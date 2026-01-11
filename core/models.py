from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.
class User(AbstractUser):
  email = models.EmailField(unique=True)
  
  USERNAME_FIELD = 'email'
  REQUIRED_FIELDS = ['username']

@receiver(post_save, sender=User)
def create_vendor_profile(sender, instance, created, **kwargs):
    from django.db import transaction
    from store.models import Vendor
    
    def handle_vendor_creation():
        if instance.is_staff and not Vendor.objects.filter(user=instance).exists():
            Vendor.objects.create(
                user=instance,
                name=f"{instance.first_name} {instance.last_name}" or instance.username,
                email=instance.email,
                shop_name=f"{instance.username}'s Shop"
            )
    
    transaction.on_commit(handle_vendor_creation)

class UserOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='otp')
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        from django.utils import timezone
        import datetime
        # Valid for 10 minutes
        return self.created_at >= timezone.now() - datetime.timedelta(minutes=10)
  
  
