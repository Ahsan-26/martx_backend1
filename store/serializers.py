from decimal import Decimal
from django.db import transaction
from django.db.models import Avg
from rest_framework import serializers
from django.contrib.auth import get_user_model
from payments.models import Payment
from .signals import order_created
from .models import Cart, CartItem, Customer, Order, OrderItem, Product, Collection, Review, ProductImage, Vendor, \
    VendorImage
from django.contrib.auth import get_user_model  # Use this to get the custom user model

import uuid  # For generating a unique part for the username
from core.utils_sentiment import analyze_sentiment

class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ['id', 'title', 'products_count']

    products_count = serializers.IntegerField(read_only=True)


class ProductImageSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        product_id = self.context["product_id"]
        return ProductImage.objects.create(product_id=product_id, **validated_data)

    class Meta:
        model = ProductImage
        fields = ["id", "image"]


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    vendor = serializers.StringRelatedField(read_only=True)
    average_rating = serializers.SerializerMethodField()
    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'slug', 'inventory',
                  'unit_price', 'price_with_tax', 'collection', 'images', 'vendor', 'average_rating', 'reviews_breakdown']

    price_with_tax = serializers.SerializerMethodField(
        method_name='calculate_tax')

    def calculate_tax(self, product: Product):
        return product.unit_price * Decimal(1.1)
    
    def create(self, validated_data):
        images_data = self.context.get('request').FILES
        product = Product.objects.create(**validated_data)
        for image_data in images_data.getlist('images'):
            ProductImage.objects.create(product=product, image=image_data)
        return product

    def update(self, instance, validated_data):
        images_data = self.context.get('request').FILES
        
        # Update standard fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Handle images if provided
        if images_data.getlist('images'):
             # Optional: clear old images? Or append? Let's append for now or strict replace?
             # User prompt implies "Add Product" and "Update Product". 
             # For update, typically we add to existing or replace. 
             # Let's keep existing and add new ones for now, or clear if needed.
             # Given "Update images for existing products", usually implies replacement or addition.
             # Let's just add for now.
             for image_data in images_data.getlist('images'):
                 ProductImage.objects.create(product=instance, image=image_data)
        
        return instance

    def get_average_rating(self, product: Product):
        # Assuming `average_rating` is calculated as an aggregation of related reviews
        return product.reviews.aggregate(average=Avg('rating'))['average'] or 0.0

    reviews_breakdown = serializers.SerializerMethodField()

    def get_reviews_breakdown(self, product: Product):
        reviews = product.reviews.all()
        total_reviews = reviews.count()
        if total_reviews == 0:
            return {
                "total_reviews": 0,
                "average_rating": 0.0,
                "sentiment_counts": {"positive": 0, "neutral": 0, "negative": 0},
                "sentiment_percentages": {"positive": 0, "neutral": 0, "negative": 0}
            }
        
        # Calculate sentiment counts
        positive = reviews.filter(sentiment='positive').count()
        neutral = reviews.filter(sentiment='neutral').count()
        negative = reviews.filter(sentiment='negative').count()
        
        # Calculate percentages
        return {
            "total_reviews": total_reviews,
            "average_rating": self.get_average_rating(product),
            "sentiment_counts": {
                "positive": positive,
                "neutral": neutral,
                "negative": negative
            },
            "sentiment_percentages": {
                "positive": round((positive / total_reviews) * 100, 1),
                "neutral": round((neutral / total_reviews) * 100, 1),
                "negative": round((negative / total_reviews) * 100, 1)
            }
        }

class SimpleProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'unit_price']


class ReviewSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = ['id', 'date', 'name', 'description', 'rating', 'sentiment', 'confidence']

    def create(self, validated_data):
        product_id = self.context['product_id']
        description = validated_data.get('description', '')
        
        # Analyze sentiment
        sentiment, confidence = analyze_sentiment(description)
        
        # Remove sentiment/confidence if they exist in validated_data to avoid overrides
        validated_data.pop('sentiment', None)
        validated_data.pop('confidence', None)
        
        return Review.objects.create(
            product_id=product_id, 
            sentiment=sentiment, 
            confidence=confidence, 
            **validated_data
        )


class CartItemSerializer(serializers.ModelSerializer):
    product = SimpleProductSerializer()
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, cart_item: CartItem):
        return cart_item.quantity * cart_item.product.unit_price

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity', 'total_price']


class CartSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, cart):
        return sum([item.quantity * item.product.unit_price for item in cart.items.all()])

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_price']


class AddCartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        if not Product.objects.filter(pk=value).exists():
            raise serializers.ValidationError(
                'No product with the given ID was found.')
        return value

    def save(self, **kwargs):
        cart_id = self.context['cart_id']
        product_id = self.validated_data['product_id']
        quantity = self.validated_data['quantity']

        try:
            cart_item = CartItem.objects.get(
                cart_id=cart_id, product_id=product_id)
            cart_item.quantity += quantity
            cart_item.save()
            self.instance = cart_item
        except CartItem.DoesNotExist:
            self.instance = CartItem.objects.create(
                cart_id=cart_id, **self.validated_data)

        return self.instance

    class Meta:
        model = CartItem
        fields = ['id', 'product_id', 'quantity']


class UpdateCartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['quantity']

class VendorImageSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        vendor_id = self.context["vendor_id"]
        return VendorImage.objects.create(vendor_id=vendor_id, **validated_data)

    class Meta:
        model = VendorImage
        fields = ["id", "image"]

class VendorSerializer(serializers.ModelSerializer):
    average_rating = serializers.SerializerMethodField()
    vendor_stats = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ['id', 'name','user', 'email', 'phone','images', 'shop_name', 'shop_description', 'shop_address', 'average_rating', 'vendor_stats']

    def get_vendor_stats(self, vendor):
        # Aggregate stats from all products of this vendor
        products = vendor.products.all()
        # Flat list of all reviews for this vendor's products
        all_reviews = Review.objects.filter(product__in=products)
        total_reviews = all_reviews.count()
        
        if total_reviews == 0:
             return {
                "total_reviews": 0,
                "average_rating": 0.0,
                "sentiment_percentages": {"positive": 0, "neutral": 0, "negative": 0}
            }

        positive = all_reviews.filter(sentiment='positive').count()
        neutral = all_reviews.filter(sentiment='neutral').count()
        negative = all_reviews.filter(sentiment='negative').count()

        return {
            "total_reviews": total_reviews,
            "average_rating": vendor.average_rating(),
            "sentiment_percentages": {
                "positive": round((positive / total_reviews) * 100, 1),
                "neutral": round((neutral / total_reviews) * 100, 1),
                "negative": round((negative / total_reviews) * 100, 1)
            }
        }

    def get_average_rating(self, obj):
        return obj.average_rating()

    def validate_user(self, value):
        # Ensure the user is not already associated with a vendor
        if Vendor.objects.filter(user=value).exists():
            raise serializers.ValidationError("This user is already linked to a vendor.")
        return value

class CustomerSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Customer
        fields = ['id', 'user_id', 'phone', 'birth_date', 'membership']


class OrderItemSerializer(serializers.ModelSerializer):
    product = SimpleProductSerializer()  # This can be string related field

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'unit_price', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    payment_status = serializers.CharField(source='get_payment_status_display')
    total = serializers.SerializerMethodField()
    class Meta:
        model = Order
        fields = ['id', 'customer', 'placed_at', 'payment_status', 'items', 'total']

    def get_total(self, order):
        return sum(item.quantity * item.unit_price for item in order.items.all())

class VendorOrderItemSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='product.title')
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product_title', 'unit_price', 'quantity']

class VendorOrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    buyer_name = serializers.CharField(source='customer.user.get_full_name')
    buyer_email = serializers.EmailField(source='customer.user.email')
    payment_status = serializers.CharField(source='get_payment_status_display')

    class Meta:
        model = Order
        fields = ['id', 'placed_at', 'payment_status', 'items', 'total', 'buyer_name', 'buyer_email']

    def get_items(self, order):
        vendor = self.context.get('vendor')
        items = order.items.filter(product__vendor=vendor)
        return VendorOrderItemSerializer(items, many=True).data

    def get_total(self, order):
        vendor = self.context.get('vendor')
        items = order.items.filter(product__vendor=vendor)
        return sum(item.quantity * item.unit_price for item in items)
class UpdateOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['payment_status']


class CreateOrderSerializer(serializers.Serializer):
    cart_id = serializers.UUIDField(required=False)  # cart_id is required but only one of them should be provided
    product_id = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(default=1)

    # Fields for guest users
    name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    address = serializers.CharField(required=False)
    city = serializers.CharField(required=False)
    country = serializers.CharField(required=False)
    postal_code = serializers.CharField(required=False)

    # Add payment method field
    payment_method = serializers.ChoiceField(choices=['stripe', 'cod'], write_only=True, required=True)
    def validate(self, data):
        # Ensure either cart_id or product_id is provided
        if not data.get('cart_id') and not data.get('product_id'):
            raise serializers.ValidationError('Either cart_id or product_id must be provided.')

        user = self.context.get('user')

        # If the user is unauthenticated (guest), ensure guest fields are present
        if not user:
            required_fields = ['name', 'email', 'address', 'city', 'country', 'postal_code']
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError({field: f"{field} is required for guest checkout."})

        return data

    def save(self, **kwargs):
        with transaction.atomic():
            cart_id = self.validated_data.get('cart_id')
            product_id = self.validated_data.get('product_id')
            quantity = self.validated_data.get('quantity', 1)
            payment_method = self.validated_data.get('payment_method')  # Get payment method from request
            user = self.context.get('user')

            User = get_user_model()

            # Step 1: Handle customer retrieval or creation
            if user:
                # Authenticated user: retrieve their associated customer profile
                customer, _ = Customer.objects.get_or_create(user=user)
            else:
                # Guest user: create a guest user and customer profile
                email = self.validated_data.get('email')
                name = self.validated_data.get('name', 'Guest')

                # Generate a unique username for guest users
                username = f"{name.replace(' ', '_').lower()}_{uuid.uuid4().hex[:6]}"
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={'username': username, 'first_name': name}
                )
                customer, created = Customer.objects.get_or_create(user=user)

            # Step 2: Ensure we create a unique order for each customer (fixing the same order ID issue)

            # For cart checkout, create a new order if one doesn't exist for the user and cart
            if cart_id:
                existing_orders = Order.objects.filter(
                    customer=customer,
                    items__product__cartitem__cart_id=cart_id
                ).distinct()

                if not existing_orders.exists():
                    # Create a new order for the cart
                    cart_items = CartItem.objects.select_related('product').filter(cart_id=cart_id)
                    order = Order.objects.create(customer=customer)
                    order_items = [
                        OrderItem(order=order, product=item.product, unit_price=item.product.unit_price,
                                  quantity=item.quantity)
                        for item in cart_items
                    ]
                    OrderItem.objects.bulk_create(order_items)
                    Cart.objects.filter(pk=cart_id).delete()
                else:
                    order = existing_orders.first()

            # For single product purchase, create a new order for the user and product
            elif product_id:
                # existing_orders = Order.objects.filter(
                #     customer=customer,
                #     items__product_id=product_id
                # ).distinct()

                # if not existing_orders.exists():
                product = Product.objects.get(pk=product_id)
                order = Order.objects.create(customer=customer)
                OrderItem.objects.create(order=order, product=product, unit_price=product.unit_price,
                                             quantity=quantity)
                # else:
                #     order = existing_orders.first()

            # Step 3: Handle payment creation or retry logic
            existing_payment = Payment.objects.filter(order=order).first()

            if existing_payment:
                if existing_payment.status == Payment.COMPLETED:
                    raise serializers.ValidationError(f"Payment for Order {order.id} has already been completed.")
                else:
                    # Retry payment if pending or failed
                    existing_payment.status = Payment.PENDING
                    existing_payment.payment_method = payment_method
                    existing_payment.save()
                    payment = existing_payment
            else:
                # Create a new payment
                if payment_method == 'cod':
                    payment_status = Payment.PENDING  # Set COD payments as 'pending'
                else:
                    payment_status = Payment.PENDING  # Default for 'stripe' or other methods


                # Refresh order to ensure items are recognized for total calculation
                order.refresh_from_db()

                payment = Payment.objects.create(
                    order=order,
                    amount=order.calculate_total_amount(),
                    status=payment_status,
                    payment_method=payment_method # Can be changed dynamically based on user's choice
                )

            # Step 4: Trigger order_created signal (if needed)
            # Ensure order is refreshed before sending signal
            if order.items.count() == 0:
                order.refresh_from_db()

            order_created.send_robust(self.__class__, order=order)

            return order


class AuthenticatedOrderSerializer(serializers.Serializer):
    cart_id = serializers.UUIDField(required=False)
    product_id = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(default=1)


    # Add payment method field
    payment_method = serializers.ChoiceField(choices=['stripe', 'cod'], write_only=True, required=True)

    def validate(self, data):
        if not data.get('cart_id') and not data.get('product_id'):
            raise serializers.ValidationError('Either cart_id or product_id must be provided.')
        return data

    def save(self, **kwargs):
        user = self.context['user']
        if not user:
            raise serializers.ValidationError("User must be authenticated.")

        # Fetch customer associated with authenticated user
        customer = Customer.objects.get(user=user)

        # Create or retrieve the order for the authenticated user
        order = None
        cart_id = self.validated_data.get('cart_id')
        product_id = self.validated_data.get('product_id')
        quantity = self.validated_data.get('quantity', 1)

        if cart_id:
            cart_items = CartItem.objects.select_related('product').filter(cart_id=cart_id)
            order = Order.objects.create(customer=customer)
            order_items = [
                OrderItem(order=order, product=item.product, unit_price=item.product.unit_price, quantity=item.quantity)
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)
            Cart.objects.filter(pk=cart_id).delete()

        elif product_id:
            product = Product.objects.get(pk=product_id)
            order = Order.objects.create(customer=customer)
            OrderItem.objects.create(order=order, product=product, unit_price=product.unit_price, quantity=quantity)

        # Handle payment creation
        payment_method = self.validated_data.get('payment_method')
        if payment_method == 'cod':
            payment_status = Payment.PENDING
        else:
            payment_status = Payment.PENDING

        # Refresh order to ensure total_amount calculation includes items
        order.refresh_from_db()

        payment = Payment.objects.create(
            order=order,
            amount=order.calculate_total_amount(),
            status=payment_status,
            payment_method=payment_method  # Change if necessary
        )

        # Trigger the order_created signal
        order_created.send_robust(self.__class__, order=order)

        return order


class GuestOrderSerializer(serializers.Serializer):
    cart_id = serializers.UUIDField(required=False)
    product_id = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(default=1)
    name = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    address = serializers.CharField(required=True)
    city = serializers.CharField(required=True)
    country = serializers.CharField(required=True)
    postal_code = serializers.CharField(required=True)

    # Add payment method field
    payment_method = serializers.ChoiceField(choices=['stripe', 'cod'], write_only=True, required=True)

    def validate(self, data):
        if not data.get('cart_id') and not data.get('product_id'):
            raise serializers.ValidationError('Either cart_id or product_id must be provided.')
        return data

    def save(self, **kwargs):
        email = self.validated_data.get('email')
        name = self.validated_data.get('name', 'Guest')

        # Create guest user
        username = f"{name.replace(' ', '_').lower()}_{uuid.uuid4().hex[:6]}"
        user, created = get_user_model().objects.get_or_create(
            email=email,
            defaults={'username': username, 'first_name': name}
        )
        customer, created = Customer.objects.get_or_create(user=user)

        # Create or retrieve the order for guest user
        order = None
        cart_id = self.validated_data.get('cart_id')
        product_id = self.validated_data.get('product_id')
        quantity = self.validated_data.get('quantity', 1)

        if cart_id:
            cart_items = CartItem.objects.select_related('product').filter(cart_id=cart_id)
            order = Order.objects.create(customer=customer)
            order_items = [
                OrderItem(order=order, product=item.product, unit_price=item.product.unit_price, quantity=item.quantity)
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)
            Cart.objects.filter(pk=cart_id).delete()

        elif product_id:
            product = Product.objects.get(pk=product_id)
            order = Order.objects.create(customer=customer)
            OrderItem.objects.create(order=order, product=product, unit_price=product.unit_price, quantity=quantity)

        # Handle payment creation
        payment_method = self.validated_data.get('payment_method')
        if payment_method == 'cod':
            payment_status = Payment.PENDING  # COD payments are initially pending
        else:
            payment_status = Payment.PENDING  # Set for 'stripe' or other methods

        # Refresh order to ensure total_amount calculation includes items
        order.refresh_from_db()

        payment = Payment.objects.create(
            order=order,
            amount=order.calculate_total_amount(),
            status=payment_status,
            payment_method=payment_method  # Can be changed dynamically based on user's choice
        )

        # Trigger the order_created signal
        order_created.send_robust(self.__class__, order=order)

        return order












