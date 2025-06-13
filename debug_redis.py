#!/usr/bin/env python3
"""
Debug Redis connections for both local and UPSTASH
"""

import os
import redis
from dotenv import load_dotenv

load_dotenv()

def test_local_redis():
    """Test local Redis connection"""
    print("🏠 Testing Local Redis...")
    
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    print(f"   URL: {redis_url}")
    
    try:
        # Parse Redis URL
        import urllib.parse
        parsed = urllib.parse.urlparse(redis_url)
        
        config = {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 6379,
            'db': int(parsed.path[1:]) if parsed.path and len(parsed.path) > 1 else 0,
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True
        }
        
        print(f"   Config: {config}")
        
        r = redis.Redis(**config)
        response = r.ping()
        
        if response:
            print("   ✅ Local Redis connection successful")
            
            # Test basic operations
            r.set('test_key', 'test_value', ex=60)
            value = r.get('test_key')
            print(f"   ✅ Read/write test: {value}")
            r.delete('test_key')
            
            # Get info
            info = r.info()
            print(f"   📊 Redis version: {info.get('redis_version', 'unknown')}")
            print(f"   📊 Connected clients: {info.get('connected_clients', 0)}")
            
            return True
        else:
            print("   ❌ Ping failed")
            return False
            
    except Exception as e:
        print(f"   ❌ Local Redis failed: {e}")
        return False

def test_upstash_redis():
    """Test UPSTASH Redis connection"""
    print("\n🌐 Testing UPSTASH Redis...")
    
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    if not upstash_url or not upstash_token:
        print("   ⚠️  UPSTASH credentials not found in environment")
        print(f"   UPSTASH_REDIS_URL: {'SET' if upstash_url else 'NOT SET'}")
        print(f"   UPSTASH_REDIS_REST_TOKEN: {'SET' if upstash_token else 'NOT SET'}")
        return False
    
    print(f"   URL: {upstash_url}")
    print(f"   Token: {upstash_token[:10]}...{upstash_token[-4:] if len(upstash_token) > 14 else upstash_token}")
    
    try:
        # Parse UPSTASH URL
        import urllib.parse
        parsed = urllib.parse.urlparse(upstash_url)
        
        config = {
            'host': parsed.hostname,
            'port': parsed.port or 6379,
            'password': upstash_token,
            'ssl': True,
            'ssl_cert_reqs': None,
            'decode_responses': True,
            'socket_connect_timeout': 30,
            'socket_timeout': 30,
            'retry_on_timeout': True,
            'health_check_interval': 30
        }
        
        print(f"   Config: {config}")
        
        r = redis.Redis(**config)
        response = r.ping()
        
        if response:
            print("   ✅ UPSTASH Redis connection successful")
            
            # Test basic operations
            r.set('test_key', 'test_value', ex=60)
            value = r.get('test_key')
            print(f"   ✅ Read/write test: {value}")
            r.delete('test_key')
            
            # Get info (may not be available on UPSTASH)
            try:
                info = r.info()
                print(f"   📊 Redis version: {info.get('redis_version', 'unknown')}")
            except:
                print("   📊 Redis info not available (normal for UPSTASH)")
            
            return True
        else:
            print("   ❌ Ping failed")
            return False
            
    except Exception as e:
        print(f"   ❌ UPSTASH Redis failed: {e}")
        return False

def check_redis_server():
    """Check if Redis server is running locally"""
    print("\n🔍 Checking local Redis server...")
    
    import subprocess
    
    # Check if Redis is running
    try:
        # Try to connect to default Redis port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 6379))
        sock.close()
        
        if result == 0:
            print("   ✅ Redis server is running on localhost:6379")
            
            # Try redis-cli ping
            try:
                result = subprocess.run(['redis-cli', 'ping'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'PONG' in result.stdout:
                    print("   ✅ redis-cli ping successful")
                else:
                    print(f"   ⚠️  redis-cli ping failed: {result.stdout}")
            except Exception as e:
                print(f"   ⚠️  redis-cli not available: {e}")
                
        else:
            print("   ❌ No Redis server running on localhost:6379")
            print("   💡 Start Redis with: redis-server")
            print("   💡 Or install Redis: sudo apt install redis-server")
            
    except Exception as e:
        print(f"   ❌ Failed to check Redis server: {e}")

def main():
    """Main debug function"""
    print("🔧 Redis Connection Debugger")
    print("=" * 50)
    
    # Show environment
    environment = os.getenv('ENVIRONMENT', 'development')
    print(f"Environment: {environment}")
    
    # Check local Redis server
    check_redis_server()
    
    # Test local Redis connection
    local_success = test_local_redis()
    
    # Test UPSTASH Redis connection
    upstash_success = test_upstash_redis()
    
    print("\n📊 Summary:")
    print(f"   Local Redis:   {'✅ Working' if local_success else '❌ Failed'}")
    print(f"   UPSTASH Redis: {'✅ Working' if upstash_success else '❌ Failed'}")
    
    if not local_success and not upstash_success:
        print("\n🚨 Both Redis connections failed!")
        print("\n💡 Possible solutions:")
        print("   1. Start local Redis: redis-server")
        print("   2. Install Redis: sudo apt install redis-server")
        print("   3. Check UPSTASH credentials in .env file")
        print("   4. Verify UPSTASH Redis URL format")
        
    elif local_success:
        print("\n✅ Local Redis is working - you can use development mode")
        
    elif upstash_success:
        print("\n✅ UPSTASH Redis is working - you can use production mode")

if __name__ == '__main__':
    main()