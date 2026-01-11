from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
class User(AbstractUser):
  email = models.EmailField(unique=True)
  
  USERNAME_FIELD = 'email'
  REQUIRED_FIELDS = ['username']

class UserOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='otp')
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        from django.utils import timezone
        import datetime
        # Valid for 10 minutes
        return self.created_at >= timezone.now() - datetime.timedelta(minutes=10)
  
  
