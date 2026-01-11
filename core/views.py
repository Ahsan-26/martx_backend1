from rest_framework import status, views
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import User, UserOTP
from .serializers import SignupSerializer, VerifyOTPSerializer
from rest_framework_simplejwt.tokens import RefreshToken
import random
import logging

logger = logging.getLogger(__name__)

def generate_otp():
    return str(random.randint(100000, 999999))

class SignupView(views.APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            otp_code = generate_otp()
            UserOTP.objects.create(user=user, otp_code=otp_code)
            
            # Send Email
            subject = "Your MartX Verification Code"
            message = f"Hi {user.username},\n\nYour verification code is: {otp_code}\n\nThis code will expire in 10 minutes."
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
            except Exception as e:
                logger.error(f"Failed to send email to {user.email}: {str(e)}")
                # Even if email fails, user is created but can't verify. 
                # We return an error so the user knows why they didn't get the code.
                return Response({"error": "Signup successful, but failed to send verification email. Please use the 'Resend Code' option."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"message": "Signup successful. Please verify your email with the OTP sent."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(views.APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp_code = serializer.validated_data['otp_code']
            
            try:
                user = User.objects.get(email=email)
                user_otp = UserOTP.objects.get(user=user, otp_code=otp_code)
                
                if user_otp.is_valid():
                    user.is_active = True
                    user.save()
                    user_otp.delete()
                    
                    # Generate JWT Token
                    refresh = RefreshToken.for_user(user)
                    return Response({
                        "message": "Account verified successfully.",
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                        "user": {
                            "username": user.username,
                            "email": user.email
                        }
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({"error": "OTP expired."}, status=status.HTTP_400_BAD_REQUEST)
            except (User.DoesNotExist, UserOTP.DoesNotExist):
                return Response({"error": "Invalid email or OTP code."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(views.APIView):
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
            if user.is_active:
                return Response({"message": "Account is already active."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Delete old OTP if exists
            UserOTP.objects.filter(user=user).delete()
            
            otp_code = generate_otp()
            UserOTP.objects.create(user=user, otp_code=otp_code)
            
            subject = "Your MartX Verification Code (Resend)"
            message = f"Hi {user.username},\n\nYour new verification code is: {otp_code}\n\nThis code will expire in 10 minutes."
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
            
            return Response({"message": "OTP resent successfully."}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User with this email does not exist."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error resending OTP to {email}: {str(e)}")
            return Response({"error": "Failed to resend email. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
