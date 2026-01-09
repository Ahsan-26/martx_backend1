import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def analyze_sentiment(text):
    """
    Analyzes the sentiment of the given text using APILayer Sentiment Analysis API.
    Returns a tuple: (sentiment_label, confidence_score)
    Default: ('neutral', 0.0) on error.
    """
    if not text:
        return 'neutral', 0.0

    api_key = getattr(settings, 'APILAYER_API_KEY', None)
    if not api_key:
        logger.error("APILAYER_API_KEY is missing.")
        return 'neutral', 0.0

    # APILayer Sentiment URL
    url = "https://api.apilayer.com/sentiment/analysis"
    
    headers = {
        "apikey": api_key
    }
    
    # The API expects the body to be the raw text or sometimes a specific parameter based on exact endpoint doc.
    # Checking standard APILayer Sentiment docs: usually POST with body as text.
    # Let's try sending as payload directly.
    try:
        response = requests.post(url, headers=headers, data=text.encode('utf-8'), timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            # typical response: {"sentiment": "positive", "confidence": 0.99, ...}
            # Adjust based on actua API response structure. 
            # If structure is different, we catch and default.
            sentiment = data.get('sentiment', 'neutral').lower()
            confidence = data.get('confidence', 0.0)
            return sentiment, confidence
        else:
            logger.error(f"Sentiment API Error: {response.status_code} - {response.text}")
            return 'neutral', 0.0

    except Exception as e:
        logger.error(f"Sentiment Analysis Failed: {e}")
        return 'neutral', 0.0
