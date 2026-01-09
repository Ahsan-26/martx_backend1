import requests
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_exchange_rates(request):
    """
    Fetches the latest exchange rates from APILayer (Fixer/Exchangerates Data).
    Functions as a proxy to hide the API key from the frontend.
    """
    # Check for API Key
    api_key = getattr(settings, 'APILAYER_API_KEY', None)
    if not api_key:
        logger.error("APILAYER_API_KEY is missing in settings.")
        return Response(
            {"error": "Server configuration error: API Key missing."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Base URL for APILayer Exchange Rates Data API
    # Note: 'fixer' endpoint on apilayer is often 'https://api.apilayer.com/fixer/latest'
    # or 'https://api.apilayer.com/exchangerates_data/latest'
    url = "https://api.apilayer.com/exchangerates_data/latest"
    
    # Parameters
    base_currency = request.query_params.get('base', 'USD')
    symbols = request.query_params.get('symbols', 'EUR,GBP,CNY,JPY,CAD,AUD,INR,PKR')

    headers = {
        "apikey": api_key
    }
    
    params = {
        "base": base_currency,
        "symbols": symbols
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            return Response(response.json())
        else:
            logger.error(f"APILayer API Error: {response.status_code} - {response.text}")
            return Response(
                {"error": "Failed to fetch exchange rates.", "details": response.json().get('message', '')}, 
                status=response.status_code
            )
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return Response(
            {"error": "External service unavailable."}, 
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
