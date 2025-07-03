"""
Redis configuration module
Handles both local Redis and UPSTASH Redis for production
"""
import os
import redis
from dotenv import load_dotenv

load_dotenv()

def get_redis_config():
    """Establishes and returns a Redis connection based on the environment."""
    
    # First, always try UPSTASH if the URL is available
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    
    if upstash_url and upstash_url != 'your_upstash_redis_url_here':
        print("🌐 Using UPSTASH Redis")
        # Ensure the URL starts with rediss:// for SSL connections
        if not upstash_url.startswith('rediss://'):
            upstash_url = 'rediss://' + upstash_url.split('://', 1)[-1]
        
        redis_url = upstash_url
    else:
        # Fallback to local Redis
        print("🏠 Using local Redis")
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    try:
        # Use from_url which correctly handles all connection parameters including SSL for rediss://
        # Add a longer timeout for cloud environments
        r = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=20, # Increased timeout
            retry_on_timeout=True
        )
        # Test connection
        r.ping()
        print("✅ Redis connection successful")
        return r
    except redis.exceptions.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        # Raising the exception will stop the app from starting with a bad connection
        raise
    except Exception as e:
        print(f"❌ An unexpected error occurred during Redis connection: {e}")
        raise

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
    """Get UPSTASH specific configuration - auto-generated from successful test"""
    
    # Extract hostname from URL
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    
    # Use the simple working configuration from the test
    return {
        'host': hostname,
        'port': 31889,  # UPSTASH Redis port
        'password': upstash_token,
        'ssl': True,
        'decode_responses': True
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
            # Extract hostname from URL
            hostname = upstash_url.replace('https://', '').replace('http://', '')
            
            # Use secure rediss:// URL (this worked in our test)
            broker_url = f"rediss://:{upstash_token}@{hostname}:31889/0"
            print(f"🔗 Celery broker: UPSTASH Redis (secure)")
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