#!/usr/bin/env python3
"""
Comprehensive UPSTASH Redis testing with different configurations
"""

import os
import redis
import time
from dotenv import load_dotenv

load_dotenv()

def test_upstash_configurations():
    """Test multiple UPSTASH Redis configurations to find what works"""
    
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    if not upstash_url or not upstash_token:
        print("❌ UPSTASH credentials not found")
        return False
    
    print(f"🔧 Testing UPSTASH Redis configurations...")
    print(f"   URL: {upstash_url}")
    print(f"   Token: {upstash_token[:10]}...{upstash_token[-4:]}")
    
    # Extract hostname from URL
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    
    configurations = [
        {
            'name': 'Config 1: Basic SSL',
            'config': {
                'host': hostname,
                'port': 6379,
                'password': upstash_token,
                'ssl': True,
                'decode_responses': True
            }
        },
        {
            'name': 'Config 2: SSL with cert handling',
            'config': {
                'host': hostname,
                'port': 6379,
                'password': upstash_token,
                'ssl': True,
                'ssl_cert_reqs': None,
                'ssl_check_hostname': False,
                'decode_responses': True
            }
        },
        {
            'name': 'Config 3: Extended timeouts',
            'config': {
                'host': hostname,
                'port': 6379,
                'password': upstash_token,
                'ssl': True,
                'ssl_cert_reqs': None,
                'ssl_check_hostname': False,
                'decode_responses': True,
                'socket_connect_timeout': 30,
                'socket_timeout': 30,
                'retry_on_timeout': True
            }
        },
        {
            'name': 'Config 4: Connection pool settings',
            'config': {
                'host': hostname,
                'port': 6379,
                'password': upstash_token,
                'ssl': True,
                'ssl_cert_reqs': None,
                'ssl_check_hostname': False,
                'decode_responses': True,
                'socket_connect_timeout': 20,
                'socket_timeout': 20,
                'retry_on_timeout': True,
                'connection_pool_class_kwargs': {
                    'max_connections': 1,
                    'retry_on_timeout': True
                }
            }
        },
        {
            'name': 'Config 5: Minimal settings',
            'config': {
                'host': hostname,
                'port': 6379,
                'password': upstash_token,
                'ssl': True,
                'socket_connect_timeout': 10,
                'socket_timeout': 10
            }
        }
    ]
    
    working_config = None
    
    for test_config in configurations:
        print(f"\n🧪 Testing: {test_config['name']}")
        
        try:
            r = redis.Redis(**test_config['config'])
            
            # Test connection
            start_time = time.time()
            result = r.ping()
            response_time = time.time() - start_time
            
            if result:
                print(f"   ✅ Ping successful ({response_time:.2f}s)")
                
                # Test basic operations
                try:
                    r.set('test_key', 'test_value', ex=60)
                    value = r.get('test_key')
                    if value == 'test_value':
                        print(f"   ✅ Read/write test successful")
                        r.delete('test_key')
                        
                        # Test pipeline
                        pipe = r.pipeline()
                        pipe.set('pipe_test', 'pipe_value')
                        pipe.get('pipe_test')
                        pipe.delete('pipe_test')
                        results = pipe.execute()
                        print(f"   ✅ Pipeline test successful")
                        
                        print(f"   🎉 Configuration WORKS!")
                        working_config = test_config
                        break
                    else:
                        print(f"   ❌ Read/write test failed")
                        
                except Exception as e:
                    print(f"   ❌ Read/write test error: {e}")
            else:
                print(f"   ❌ Ping failed")
                
        except Exception as e:
            print(f"   ❌ Connection failed: {e}")
    
    if working_config:
        print(f"\n🎉 Found working configuration: {working_config['name']}")
        print(f"📋 Config: {working_config['config']}")
        return working_config['config']
    else:
        print(f"\n❌ No working configurations found")
        return None

def generate_redis_config_file(working_config):
    """Generate updated redis_config.py with working UPSTASH settings"""
    
    if not working_config:
        print("❌ No working config to generate file")
        return
    
    config_code = f"""def get_upstash_config(upstash_url, upstash_token):
    \"\"\"Get UPSTASH specific configuration - auto-generated from successful test\"\"\"
    
    # Extract hostname from URL
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    
    return {working_config}
"""
    
    print(f"\n📝 Generated working UPSTASH configuration:")
    print(config_code)
    
    # Optionally write to file
    try:
        with open('upstash_config_working.py', 'w') as f:
            f.write(config_code)
        print(f"✅ Saved working config to upstash_config_working.py")
    except Exception as e:
        print(f"❌ Failed to save config: {e}")

def test_celery_broker_url():
    """Test UPSTASH as Celery broker"""
    
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    if not upstash_url or not upstash_token:
        return
    
    print(f"\n🔗 Testing UPSTASH as Celery broker...")
    
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    
    # Different broker URL formats
    broker_formats = [
        f"redis://:{upstash_token}@{hostname}:6379/0",
        f"rediss://:{upstash_token}@{hostname}:6379/0",
        f"redis://{hostname}:6379/0?password={upstash_token}",
        f"rediss://{hostname}:6379/0?password={upstash_token}"
    ]
    
    for broker_url in broker_formats:
        print(f"   Testing: {broker_url[:50]}...")
        
        try:
            # Simple connection test
            import urllib.parse
            parsed = urllib.parse.urlparse(broker_url)
            
            r = redis.Redis(
                host=parsed.hostname,
                port=parsed.port or 6379,
                password=parsed.password or upstash_token,
                ssl=parsed.scheme == 'rediss',
                ssl_cert_reqs=None,
                ssl_check_hostname=False,
                socket_connect_timeout=10
            )
            
            result = r.ping()
            if result:
                print(f"   ✅ Broker URL works: {broker_url[:50]}...")
                return broker_url
            else:
                print(f"   ❌ Ping failed")
                
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    print(f"   ❌ No working broker URLs found")
    return None

if __name__ == '__main__':
    print("🚀 UPSTASH Redis Comprehensive Test")
    print("=" * 50)
    
    # Test different configurations
    working_config = test_upstash_configurations()
    
    # Generate config file if we found a working configuration
    if working_config:
        generate_redis_config_file(working_config)
    
    # Test as Celery broker
    working_broker = test_celery_broker_url()
    
    print(f"\n📊 Summary:")
    print(f"   Redis Connection: {'✅ Found working config' if working_config else '❌ No working config'}")
    print(f"   Celery Broker:    {'✅ Found working URL' if working_broker else '❌ No working URL'}")
    
    if working_config and working_broker:
        print(f"\n🎉 UPSTASH Redis is ready for production!")
        print(f"💡 Next steps:")
        print(f"   1. Update redis_config.py with the working configuration")
        print(f"   2. Set ENVIRONMENT=production in .env")
        print(f"   3. Restart the application")
    else:
        print(f"\n⚠️  UPSTASH Redis needs further investigation")
        print(f"💡 You can continue using local Redis for now")