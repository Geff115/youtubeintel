"""
Rate limiting middleware for YouTubeIntel API
Implements per-user rate limiting with Redis backend
"""

import os
import json
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from app.redis_config import get_redis_connection
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        try:
            self.redis_client = get_redis_connection()
            self.default_limits = {
                'requests_per_minute': int(os.getenv('RATE_LIMIT_REQUESTS_PER_MINUTE', '60')),
                'requests_per_hour': int(os.getenv('RATE_LIMIT_REQUESTS_PER_HOUR', '1000')),
                'requests_per_day': int(os.getenv('RATE_LIMIT_REQUESTS_PER_DAY', '10000')),
                'credits_per_hour': int(os.getenv('RATE_LIMIT_CREDITS_PER_HOUR', '500')),
                'credits_per_day': int(os.getenv('RATE_LIMIT_CREDITS_PER_DAY', '2000'))
            }
            
            # Plan-based limits
            self.plan_limits = {
                'free': {
                    'requests_per_minute': 10,
                    'requests_per_hour': 100,
                    'requests_per_day': 500,
                    'credits_per_hour': 50,
                    'credits_per_day': 100
                },
                'starter': {
                    'requests_per_minute': 30,
                    'requests_per_hour': 500,
                    'requests_per_day': 2000,
                    'credits_per_hour': 200,
                    'credits_per_day': 500
                },
                'professional': {
                    'requests_per_minute': 60,
                    'requests_per_hour': 1000,
                    'requests_per_day': 5000,
                    'credits_per_hour': 500,
                    'credits_per_day': 2000
                },
                'business': {
                    'requests_per_minute': 120,
                    'requests_per_hour': 2000,
                    'requests_per_day': 10000,
                    'credits_per_hour': 1000,
                    'credits_per_day': 5000
                },
                'enterprise': {
                    'requests_per_minute': 300,
                    'requests_per_hour': 5000,
                    'requests_per_day': 25000,
                    'credits_per_hour': 2500,
                    'credits_per_day': 10000
                }
            }
            
        except Exception as e:
            logger.error(f"Rate limiter initialization failed: {str(e)}")
            self.redis_client = None
    
    def get_user_limits(self, user_plan: str) -> dict:
        """Get rate limits for user based on their plan"""
        return self.plan_limits.get(user_plan, self.plan_limits['free'])
    
    def get_rate_limit_key(self, user_id: str, limit_type: str, window: str) -> str:
        """Generate Redis key for rate limiting"""
        timestamp = int(time.time())
        
        if window == 'minute':
            window_start = timestamp - (timestamp % 60)
        elif window == 'hour':
            window_start = timestamp - (timestamp % 3600)
        elif window == 'day':
            window_start = timestamp - (timestamp % 86400)
        else:
            window_start = timestamp
        
        return f"rate_limit:{user_id}:{limit_type}:{window}:{window_start}"
    
    def check_rate_limit(self, user_id: str, user_plan: str, limit_type: str = 'requests', 
                        credits_cost: int = 0) -> dict:
        """Check if user has exceeded rate limits"""
        if not self.redis_client:
            logger.warning("Redis not available - rate limiting disabled")
            return {'allowed': True, 'remaining': 999999}
        
        try:
            limits = self.get_user_limits(user_plan)
            current_time = time.time()
            
            # Check different time windows
            windows_to_check = ['minute', 'hour', 'day']
            
            for window in windows_to_check:
                # Get limit for this window
                if limit_type == 'requests':
                    limit_key = f'requests_per_{window}'
                elif limit_type == 'credits':
                    limit_key = f'credits_per_{window}'
                else:
                    continue
                
                max_allowed = limits.get(limit_key, 0)
                if max_allowed == 0:
                    continue
                
                # Get Redis key
                redis_key = self.get_rate_limit_key(user_id, limit_type, window)
                
                # Get current usage
                current_usage = self.redis_client.get(redis_key)
                current_usage = int(current_usage) if current_usage else 0
                
                # Calculate what usage would be after this request
                if limit_type == 'credits':
                    new_usage = current_usage + credits_cost
                else:
                    new_usage = current_usage + 1
                
                # Check if it would exceed limit
                if new_usage > max_allowed:
                    return {
                        'allowed': False,
                        'limit_exceeded': window,
                        'current_usage': current_usage,
                        'max_allowed': max_allowed,
                        'remaining': max(0, max_allowed - current_usage),
                        'retry_after': self.get_retry_after(window)
                    }
            
            return {'allowed': True}
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            # If Redis fails, allow the request but log the error
            return {'allowed': True, 'error': 'Rate limit check failed'}
    
    def increment_usage(self, user_id: str, limit_type: str = 'requests', 
                       credits_cost: int = 0) -> bool:
        """Increment usage counters"""
        if not self.redis_client:
            return True
        
        try:
            current_time = time.time()
            windows = ['minute', 'hour', 'day']
            
            for window in windows:
                redis_key = self.get_rate_limit_key(user_id, limit_type, window)
                
                # Increment counter
                if limit_type == 'credits':
                    increment_by = credits_cost
                else:
                    increment_by = 1
                
                self.redis_client.incr(redis_key, increment_by)
                
                # Set expiry based on window
                if window == 'minute':
                    self.redis_client.expire(redis_key, 120)  # 2 minutes
                elif window == 'hour':
                    self.redis_client.expire(redis_key, 7200)  # 2 hours
                elif window == 'day':
                    self.redis_client.expire(redis_key, 172800)  # 2 days
            
            return True
            
        except Exception as e:
            logger.error(f"Usage increment failed: {str(e)}")
            return False
    
    def get_retry_after(self, window: str) -> int:
        """Get retry after seconds for different windows"""
        if window == 'minute':
            return 60
        elif window == 'hour':
            return 3600
        elif window == 'day':
            return 86400
        return 60
    
    def get_current_usage(self, user_id: str, user_plan: str) -> dict:
        """Get current usage stats for user"""
        if not self.redis_client:
            return {}
        
        try:
            limits = self.get_user_limits(user_plan)
            usage_stats = {}
            
            for limit_type in ['requests', 'credits']:
                usage_stats[limit_type] = {}
                
                for window in ['minute', 'hour', 'day']:
                    redis_key = self.get_rate_limit_key(user_id, limit_type, window)
                    current_usage = self.redis_client.get(redis_key)
                    current_usage = int(current_usage) if current_usage else 0
                    
                    limit_key = f'{limit_type}_per_{window}'
                    max_allowed = limits.get(limit_key, 0)
                    
                    usage_stats[limit_type][window] = {
                        'current': current_usage,
                        'limit': max_allowed,
                        'remaining': max(0, max_allowed - current_usage),
                        'percentage': (current_usage / max_allowed * 100) if max_allowed > 0 else 0
                    }
            
            return usage_stats
            
        except Exception as e:
            logger.error(f"Usage stats retrieval failed: {str(e)}")
            return {}
    
    def reset_user_limits(self, user_id: str):
        """Reset all rate limits for a user (admin function)"""
        if not self.redis_client:
            return False
        
        try:
            pattern = f"rate_limit:{user_id}:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Reset rate limits for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limit reset failed: {str(e)}")
            return False


# Initialize global rate limiter
rate_limiter = RateLimiter()

# Rate limiting decorators
def rate_limit(credits_cost: int = 0, limit_type: str = 'requests'):
    """Decorator for rate limiting API endpoints"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Skip rate limiting if no user is authenticated
            if not hasattr(request, 'current_user'):
                return f(*args, **kwargs)
            
            user_id = request.current_user['id']
            
            # Get user plan from database
            from app.models import User
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            user_plan = user.current_plan or 'free'
            
            # Check rate limits
            rate_check = rate_limiter.check_rate_limit(
                user_id=user_id,
                user_plan=user_plan,
                limit_type=limit_type,
                credits_cost=credits_cost
            )
            
            if not rate_check.get('allowed', False):
                response_data = {
                    'error': 'Rate limit exceeded',
                    'limit_type': limit_type,
                    'window': rate_check.get('limit_exceeded'),
                    'current_usage': rate_check.get('current_usage'),
                    'max_allowed': rate_check.get('max_allowed'),
                    'retry_after': rate_check.get('retry_after'),
                    'message': f"You have exceeded your {rate_check.get('limit_exceeded')} rate limit. Please try again later."
                }
                
                response = jsonify(response_data)
                response.status_code = 429
                response.headers['Retry-After'] = str(rate_check.get('retry_after', 60))
                return response
            
            # Check if user has enough credits for this operation
            if credits_cost > 0:
                if not user.can_afford(credits_cost):
                    return jsonify({
                        'error': 'Insufficient credits',
                        'credits_needed': credits_cost,
                        'credits_available': user.credits_balance,
                        'message': f'This operation requires {credits_cost} credits, but you only have {user.credits_balance}.'
                    }), 402  # Payment Required
            
            # Execute the function
            try:
                result = f(*args, **kwargs)
                
                # If successful, increment usage counters and deduct credits
                rate_limiter.increment_usage(
                    user_id=user_id,
                    limit_type='requests'
                )
                
                if credits_cost > 0:
                    rate_limiter.increment_usage(
                        user_id=user_id,
                        limit_type='credits',
                        credits_cost=credits_cost
                    )
                    
                    # Deduct credits from user account
                    endpoint = request.endpoint or f"{request.method} {request.path}"
                    user.deduct_credits(
                        amount=credits_cost,
                        description=f"API usage: {endpoint}",
                        endpoint=endpoint
                    )
                    
                    # Log API usage
                    from app.models import APIUsageLog, db
                    api_log = APIUsageLog(
                        user_id=user.id,
                        endpoint=endpoint,
                        method=request.method,
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent', ''),
                        response_status=200,  # Assume success for now
                        credits_used=credits_cost,
                        rate_limit_key=f"{user_id}:{endpoint}"
                    )
                    db.session.add(api_log)
                    db.session.commit()
                
                return result
                
            except Exception as e:
                # Don't increment counters if the function failed
                logger.error(f"Rate limited function failed: {str(e)}")
                raise
        
        return decorated
    return decorator

def admin_rate_limit():
    """Special rate limiting for admin endpoints"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Admin endpoints get higher limits
            if hasattr(request, 'current_user'):
                user_id = request.current_user['id']
                
                # Check admin rate limits (more lenient)
                rate_check = rate_limiter.check_rate_limit(
                    user_id=user_id,
                    user_plan='enterprise',  # Use enterprise limits for admins
                    limit_type='requests'
                )
                
                if not rate_check.get('allowed', False):
                    return jsonify({
                        'error': 'Admin rate limit exceeded',
                        'retry_after': rate_check.get('retry_after', 60)
                    }), 429
                
                # Increment usage
                rate_limiter.increment_usage(user_id=user_id, limit_type='requests')
            
            return f(*args, **kwargs)
        
        return decorated
    return decorator