"""
Redis configuration module
Handles both local Redis and UPSTASH Redis for production
"""
import os
import redis
from dotenv import load_dotenv

load_dotenv()

def get_redis_config():
    """Get Redis configuration based on environment"""
    environment = os.getenv('ENVIRONMENT', 'development')
    
    # First, always try UPSTASH if credentials are available
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    if upstash_url and upstash_token and upstash_url != 'your_upstash_redis_url_here':
        print(f"🌐 Using UPSTASH Redis (credentials found)")
        
        try:
            # UPSTASH Redis configuration - simplified for better compatibility
            import urllib.parse
            parsed = urllib.parse.urlparse(upstash_url)
            
            # For UPSTASH, we need to be more careful with SSL and connection settings
            return {
                'host': parsed.hostname,
                'port': parsed.port or 6379,
                'password': upstash_token,
                'ssl': True,  # UPSTASH requires SSL
                'ssl_cert_reqs': None,  # Don't verify SSL certificates
                'ssl_check_hostname': False,  # Don't check hostname
                'decode_responses': True,
                'socket_connect_timeout': 15,  # Longer timeout for cloud connection
                'socket_timeout': 15,
                'retry_on_timeout': True,
                'connection_pool_class_kwargs': {
                    'max_connections': 10,
                    'retry_on_timeout': True
                }
            }
        except Exception as e:
            print(f"⚠️  Failed to parse UPSTASH URL, falling back to local: {e}")
            return get_local_redis_config()
    else:
        # Use local Redis
        print(f"🏠 Using local Redis (no UPSTASH credentials or development mode)")
        return get_local_redis_config()

def get_local_redis_config():
    """Get local Redis configuration"""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Parse Redis URL
    import urllib.parse
    parsed = urllib.parse.urlparse(redis_url)
    
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 6379,
        'db': int(parsed.path[1:]) if parsed.path and len(parsed.path) > 1 else 0,
        'decode_responses': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True
    }

def get_upstash_config(upstash_url, upstash_token):
    """Get UPSTASH specific configuration"""
    import urllib.parse
    
    # UPSTASH URLs can be https:// or redis://
    if upstash_url.startswith('https://'):
        # Extract hostname from https URL
        parsed = urllib.parse.urlparse(upstash_url)
        hostname = parsed.hostname
        port = 6379  # Standard Redis port
    else:
        # Handle redis:// or rediss:// URLs
        parsed = urllib.parse.urlparse(upstash_url)
        hostname = parsed.hostname
        port = parsed.port or 6379
    
    return {
        'host': hostname,
        'port': port,
        'password': upstash_token,
        'ssl': True,  # UPSTASH always uses SSL
        'ssl_cert_reqs': None,
        'ssl_check_hostname': False,
        'decode_responses': True,
        'socket_connect_timeout': 20,
        'socket_timeout': 20,
        'retry_on_timeout': True,
        'connection_pool_class_kwargs': {
            'max_connections': 5,
            'retry_on_timeout': True
        }
    }
    """Get local Redis configuration"""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Parse Redis URL
    import urllib.parse
    parsed = urllib.parse.urlparse(redis_url)
    
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 6379,
        'db': int(parsed.path[1:]) if parsed.path and len(parsed.path) > 1 else 0,
        'decode_responses': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True
    }

def get_redis_connection():
    """Get Redis connection instance"""
    config = get_redis_config()
    
    try:
        r = redis.Redis(**config)
        # Test connection
        r.ping()
        print("✅ Redis connection successful")
        return r
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        raise

def get_celery_broker_url():
    """Get broker URL for Celery"""
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    # Try UPSTASH first if available
    if upstash_url and upstash_token and upstash_url != 'your_upstash_redis_url_here':
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(upstash_url)
            
            # Construct broker URL for Celery
            if parsed.scheme == 'rediss':
                # Use secure connection
                broker_url = f"rediss://:{upstash_token}@{parsed.hostname}:{parsed.port or 6379}/0"
            else:
                # Use regular connection
                broker_url = f"redis://:{upstash_token}@{parsed.hostname}:{parsed.port or 6379}/0"
            
            print(f"🔗 Celery broker: UPSTASH Redis ({parsed.scheme})")
            return broker_url
        except Exception as e:
            print(f"⚠️  Failed to configure UPSTASH for Celery: {e}")
    
    # Fall back to local Redis
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    print(f"🔗 Celery broker: Local Redis")
    return redis_url

def test_redis_connection():
    """Test Redis connection and return status"""
    try:
        r = get_redis_connection()
        
        # Test basic operations
        test_key = 'test_connection_key'
        test_value = 'test_value'
        
        # Set and get test
        r.set(test_key, test_value, ex=60)  # Expire in 60 seconds
        retrieved_value = r.get(test_key)
        
        if retrieved_value == test_value:
            # Clean up
            r.delete(test_key)
            
            # Get Redis info
            info = r.info()
            return {
                'status': 'success',
                'redis_version': info.get('redis_version', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'environment': os.getenv('ENVIRONMENT', 'development')
            }
        else:
            return {'status': 'error', 'message': 'Redis read/write test failed'}
            
    except Exception as e:
        return {'status': 'error', 'message': str(e)}