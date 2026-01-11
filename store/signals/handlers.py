from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from store.models import Customer, Order
from . import order_created

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_customer_for_new_user(sender, **kwargs):
  if kwargs['created']:
    Customer.objects.create(user=kwargs['instance'])

@receiver(order_created)
def on_order_created(sender, **kwargs):
    order = kwargs['order']
    customer = order.customer
    items = order.items.all()
    
    # Construct email context
    subject = f"Order Confirmation - MartX #{order.id}"
    recipient_email = customer.user.email
    
    item_list = ""
    for item in items:
        item_list += f"- {item.product.title}: {item.quantity} x Rs {item.unit_price}\n"
    
    message = f"""
Hi {customer.user.first_name or customer.user.username},

Thank you for your order! We are excited to let you know that your order #{order.id} has been successfully placed.

Order Summary:
{item_list}
Total: Rs {order.calculate_total_amount()}

We will notify you once your order is shipped.

Best regards,
The MartX Team
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [recipient_email],
        fail_silently=False,
    )