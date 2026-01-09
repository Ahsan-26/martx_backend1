from django.urls import path
from .views import LikeProductView, LikeBasedRecommendationView, WishlistView

urlpatterns = [
    path('like-product/<int:product_id>/', LikeProductView.as_view(), name='like-product'),
    path('like-recommendations/', LikeBasedRecommendationView.as_view(), name='like-recommendations'),
   path('wishlist/', WishlistView.as_view(), name='wishlist'),
]
