"""
Complete Authentication System for YouTubeIntel
Handles JWT tokens, Google OAuth, traditional signup/signin, and user sessions
"""

import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import requests
import re
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.secret_key = os.getenv('JWT_SECRET_KEY', 'your-super-secret-jwt-key-change-in-production')
        self.google_client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.jwt_expiry_hours = int(os.getenv('JWT_EXPIRY_HOURS', '24'))
        self.refresh_token_expiry_days = int(os.getenv('REFRESH_TOKEN_EXPIRY_DAYS', '30'))
        
        if not self.google_client_id:
            logger.warning("Google OAuth not configured - GOOGLE_CLIENT_ID missing")
    
    def generate_jwt_token(self, user_id: str, email: str, token_type: str = 'access') -> str:
        """Generate JWT token for user authentication"""
        try:
            if token_type == 'access':
                expiry = datetime.utcnow() + timedelta(hours=self.jwt_expiry_hours)
            elif token_type == 'refresh':
                expiry = datetime.utcnow() + timedelta(days=self.refresh_token_expiry_days)
            else:
                expiry = datetime.utcnow() + timedelta(hours=1)  # Default 1 hour
            
            payload = {
                'user_id': str(user_id),
                'email': email,
                'token_type': token_type,
                'exp': expiry,
                'iat': datetime.utcnow(),
                'iss': 'youtubeintel'
            }
            
            token = jwt.encode(payload, self.secret_key, algorithm='HS256')
            return token
            
        except Exception as e:
            logger.error(f"JWT token generation failed: {str(e)}")
            raise Exception("Token generation failed")
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=['HS256'],
                issuer='youtubeintel'
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Token has expired")
        except jwt.InvalidTokenError:
            raise Exception("Invalid token")
        except Exception as e:
            logger.error(f"JWT verification failed: {str(e)}")
            raise Exception("Token verification failed")
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        try:
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            logger.error(f"Password hashing failed: {str(e)}")
            raise Exception("Password hashing failed")
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'), 
                hashed_password.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification failed: {str(e)}")
            return False
    
    def verify_google_token(self, id_token_str: str) -> Dict[str, Any]:
        """Verify Google OAuth ID token"""
        try:
            if not self.google_client_id:
                raise Exception("Google OAuth not configured")
            
            # Verify the token
            id_info = id_token.verify_oauth2_token(
                id_token_str, 
                google_requests.Request(), 
                self.google_client_id
            )
            
            # Verify the issuer
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise Exception('Invalid issuer')
            
            return {
                'google_id': id_info['sub'],
                'email': id_info['email'],
                'name': id_info.get('name', ''),
                'first_name': id_info.get('given_name', ''),
                'last_name': id_info.get('family_name', ''),
                'picture': id_info.get('picture', ''),
                'email_verified': id_info.get('email_verified', False)
            }
            
        except Exception as e:
            logger.error(f"Google token verification failed: {str(e)}")
            raise Exception("Invalid Google token")
    
    def generate_reset_token(self) -> str:
        """Generate secure reset token"""
        return secrets.token_urlsafe(32)
    
    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def validate_password(self, password: str) -> Dict[str, Any]:
        """Validate password strength"""
        errors = []
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not re.search(r'\d', password):
            errors.append("Password must contain at least one number")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_name(self, name: str) -> bool:
        """Validate name format"""
        return len(name.strip()) >= 2 and name.replace(' ', '').isalpha()

# Initialize global auth service
auth_service = AuthService()

# Decorators for route protection
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication for OPTIONS requests
        if request.method == 'OPTIONS':
            return '', 200
            
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            try:
                # Bearer token format
                parts = auth_header.split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]
            except Exception:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            payload = auth_service.verify_jwt_token(token)
            if not payload:
                return jsonify({'error': 'Invalid or expired token'}), 401
            
            # Get user ID from either 'user_id' or 'id' field
            user_id = payload.get('user_id') or payload.get('id')
            if not user_id:
                logger.error(f"No user ID field in JWT payload. Available fields: {list(payload.keys())}")
                return jsonify({'error': 'Invalid token structure - missing user ID'}), 401
            
            # Attach user info to request with normalized 'id' field
            request.current_user = payload.copy()
            request.current_user['id'] = user_id  # Normalize to 'id' for consistency
            
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Token verification failed: {str(e)}")
            return jsonify({'error': 'Token verification failed'}), 401
    
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        # Check if user is admin (you can implement admin logic here)
        user_email = request.current_user['email']
        admin_emails = os.getenv('ADMIN_EMAILS', '').split(',')
        
        if user_email not in admin_emails:
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated

def validate_input(**validation_rules):
    """Decorator for input validation"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                data = request.get_json() or {}
                errors = {}
                
                for field, rules in validation_rules.items():
                    value = data.get(field)
                    
                    # Check required fields
                    if rules.get('required', False) and not value:
                        errors[field] = f"{field} is required"
                        continue
                    
                    if value is not None:
                        # Check type
                        expected_type = rules.get('type')
                        if expected_type and not isinstance(value, expected_type):
                            errors[field] = f"{field} must be of type {expected_type.__name__}"
                            continue
                        
                        # Check string length
                        if isinstance(value, str):
                            min_length = rules.get('min_length')
                            max_length = rules.get('max_length')
                            
                            if min_length and len(value) < min_length:
                                errors[field] = f"{field} must be at least {min_length} characters"
                            
                            if max_length and len(value) > max_length:
                                errors[field] = f"{field} must be no more than {max_length} characters"
                        
                        # Custom validation
                        custom_validator = rules.get('validator')
                        if custom_validator and not custom_validator(value):
                            errors[field] = rules.get('message', f"{field} is invalid")
                
                if errors:
                    return jsonify({'error': 'Validation failed', 'details': errors}), 400
                
                # Add validated data to request
                request.validated_data = data
                
            except Exception as e:
                return jsonify({'error': 'Invalid JSON data'}), 400
            
            return f(*args, **kwargs)
        
        return decorated
    return decorator