"""
Korapay payment integration for YouTubeIntel
"""

import os
import requests
import json
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class KorapayService:
    def __init__(self):
        self.base_url = "https://api.korapay.com/merchant"
        self.public_key = os.getenv('KORAPAY_PUBLIC_KEY')
        self.secret_key = os.getenv('KORAPAY_SECRET_KEY')
        self.encryption_key = os.getenv('KORAPAY_ENCRYPTION_KEY')
        
        # Korapay limits
        self.max_amount_kobo = 1000000  # 10,000 NGN max
        self.min_amount_kobo = 10000    # 100 NGN min
        
        if not all([self.public_key, self.secret_key]):
            logger.warning("Korapay credentials not found - payment features disabled")
    
    def create_checkout_session(self, amount_usd: float, customer_email: str, 
                               credits: int, reference: str = None) -> Dict:
        """Create a Korapay checkout session for credit purchase"""
        
        if not reference:
            reference = f"YTI_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{credits}"
        
        # Convert USD to NGN with reasonable rate
        # Should be updated with real-time rates in production via API
        # Using conservative rate to stay within Korapay limits
        usd_to_ngn_rate = 800  # Conservative rate
        amount_ngn = amount_usd * usd_to_ngn_rate
        amount_kobo = int(amount_ngn * 100)
        
        # Check Korapay limits
        if amount_kobo > self.max_amount_kobo:
            logger.error(f"Amount {amount_kobo} kobo exceeds Korapay limit of {self.max_amount_kobo}")
            return {
                'success': False, 
                'error': f'Amount too high. Maximum is ₦{self.max_amount_kobo/100:,.0f} NGN (${self.max_amount_kobo/100/usd_to_ngn_rate:.2f} USD)'
            }
        
        if amount_kobo < self.min_amount_kobo:
            logger.error(f"Amount {amount_kobo} kobo below Korapay minimum of {self.min_amount_kobo}")
            return {
                'success': False, 
                'error': f'Amount too low. Minimum is ₦{self.min_amount_kobo/100:,.0f} NGN'
            }
        
        payload = {
            "amount": amount_kobo,
            "currency": "NGN",
            "reference": reference,
            "customer": {
                "name": customer_email.split('@')[0].title(),
                "email": customer_email
            },
            "notification_url": f"{os.getenv('APP_URL', 'https://youtubeintel-backend.onrender.com')}/api/webhooks/korapay",
            "redirect_url": f"{os.getenv('FRONTEND_URL', 'https://youtubeintel.vercel.app')}/payment/success",
            "metadata": {
                "credits": credits,
                "amount_usd": amount_usd,
                "product": "YouTubeIntel Credits",
                "package_type": self._get_package_type(credits)
            }
        }
        
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Creating Korapay checkout: {credits} credits (${amount_usd} = ₦{amount_ngn} = {amount_kobo} kobo)")
            
            response = requests.post(
                f"{self.base_url}/api/v1/charges/initialize",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            logger.info(f"Korapay response status: {response.status_code}")
            logger.info(f"Korapay response: {response.text[:500]}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    logger.info(f"Checkout created successfully: {reference}")
                    return {
                        'success': True,
                        'checkout_url': result['data']['checkout_url'],
                        'reference': reference,
                        'amount_usd': amount_usd,
                        'amount_ngn': amount_ngn,
                        'amount_kobo': amount_kobo,
                        'credits': credits
                    }
            
            # Parse error response
            try:
                error_data = response.json()
                error_message = error_data.get('message', 'Payment initialization failed')
                logger.error(f"Korapay error: {error_message}")
                return {'success': False, 'error': error_message}
            except:
                logger.error(f"Korapay checkout creation failed: {response.text}")
                return {'success': False, 'error': 'Payment initialization failed'}
            
        except Exception as e:
            logger.error(f"Korapay API error: {str(e)}")
            return {'success': False, 'error': 'Payment service unavailable'}
    
    def verify_payment(self, reference: str) -> Dict:
        """Verify payment status with Korapay"""
        
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/charges/{reference}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'status': result['data']['status'],
                    'amount': result['data']['amount'],
                    'metadata': result['data'].get('metadata', {}),
                    'customer': result['data'].get('customer', {})
                }
            
            logger.error(f"Payment verification failed for {reference}: {response.text}")
            return {'success': False, 'error': 'Payment verification failed'}
            
        except Exception as e:
            logger.error(f"Payment verification error: {str(e)}")
            return {'success': False, 'error': 'Verification service unavailable'}
    
    def verify_webhook(self, payload: str, signature: str) -> bool:
        """Verify webhook signature from Korapay"""
        try:
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except:
            logger.error("Webhook signature verification failed")
            return False
    
    def _get_package_type(self, credits: int) -> str:
        """Determine package type based on credits"""
        if credits == 100:
            return 'starter'
        elif credits == 500:
            return 'professional'
        elif credits == 2000:
            return 'business'
        elif credits == 10000:
            return 'enterprise'
        else:
            return 'custom'

# Updated credit packages with Korapay-friendly pricing
CREDIT_PACKAGES = {
    'starter': {
        'credits': 100, 
        'price_usd': 9, 
        'name': 'Starter Pack',
        'description': 'Perfect for trying out YouTubeIntel',
        'features': ['100 channel discoveries', '200 full channel analyses', 'Basic support']
    },
    'professional': {
        'credits': 500, 
        'price_usd': 39,  # ₦31,200 at 800 rate = 3,120,000 kobo (over limit)
        'name': 'Professional',
        'description': 'Great for content creators and small agencies',
        'features': ['500 channel discoveries', '1,000 full channel analyses', 'Priority support', 'Data export']
    },
    'business': {
        'credits': 2000, 
        'price_usd': 129,  # Way over limit
        'name': 'Business',
        'description': 'Ideal for marketing agencies and research teams',
        'features': ['2,000 channel discoveries', '4,000 full channel analyses', 'Priority support', 'Bulk processing', 'API access']
    },
    'enterprise': {
        'credits': 10000, 
        'price_usd': 499,  # Way over limit
        'name': 'Enterprise',
        'description': 'For large organizations and extensive research',
        'features': ['10,000 channel discoveries', '20,000 full channel analyses', 'Dedicated support', 'White-label reports', 'Custom integrations']
    }
}

# Korapay-friendly packages (within the 10,000 NGN limit)
KORAPAY_PACKAGES = {
    'micro': {
        'credits': 25, 
        'price_usd': 2.5,  # ₦2,000 = 200,000 kobo
        'name': 'Micro Pack',
        'description': 'Quick top-up for immediate use',
        'features': ['25 channel discoveries', '50 full channel analyses']
    },
    'starter': {
        'credits': 100, 
        'price_usd': 9,    # ₦7,200 = 720,000 kobo
        'name': 'Starter Pack',
        'description': 'Perfect for trying out YouTubeIntel',
        'features': ['100 channel discoveries', '200 full channel analyses', 'Basic support']
    },
    'boost': {
        'credits': 150, 
        'price_usd': 12.5,  # ₦10,000 = 1,000,000 kobo (exactly at limit)
        'name': 'Boost Pack',
        'description': 'Maximum single purchase',
        'features': ['150 channel discoveries', '300 full channel analyses', 'Priority support']
    }
}

def get_package_by_credits(credits: int) -> Optional[Dict]:
    """Get package info by credit amount"""
    for package_id, package in KORAPAY_PACKAGES.items():
        if package['credits'] == credits:
            return {**package, 'id': package_id}
    return None