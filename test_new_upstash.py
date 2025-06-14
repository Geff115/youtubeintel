#!/usr/bin/env python3
"""
Test the new UPSTASH Redis database with different configurations
"""

import os
import redis
import ssl
from dotenv import load_dotenv

load_dotenv()

def test_upstash_configs():
    """Test different UPSTASH configurations"""
    
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    print(f"🔧 Testing new UPSTASH Redis database...")
    print(f"   URL: {upstash_url}")
    print(f"   Token: {upstash_token[:15]}...{upstash_token[-4:]}")
    
    # Extract host and port
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    if ':' in hostname:
        host, port = hostname.split(':')
        port = int(port)
    else:
        host = hostname
        port = 6379
    
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    
    # Test different SSL configurations
    configs = [
        {
            'name': 'Config 1: Basic SSL',
            'config': {
                'host': host,
                'port': port,
                'password': upstash_token,
                'ssl': True,
                'decode_responses': True
            }
        },
        {
            'name': 'Config 2: SSL with cert bypass',
            'config': {
                'host': host,
                'port': port,
                'password': upstash_token,
                'ssl': True,
                'ssl_cert_reqs': None,
                'ssl_check_hostname': False,
                'decode_responses': True
            }
        },
        {
            'name': 'Config 3: SSL with custom context',
            'config': {
                'host': host,
                'port': port,
                'password': upstash_token,
                'ssl': True,
                'ssl_cert_reqs': ssl.CERT_NONE,
                'ssl_check_hostname': False,
                'decode_responses': True
            }
        },
        {
            'name': 'Config 4: No SSL (if supported)',
            'config': {
                'host': host,
                'port': port,
                'password': upstash_token,
                'ssl': False,
                'decode_responses': True
            }
        },
        {
            'name': 'Config 5: Extended timeouts',
            'config': {
                'host': host,
                'port': port,
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
            'name': 'Config 6: Different SSL version',
            'config': {
                'host': host,
                'port': port,
                'password': upstash_token,
                'ssl': True,
                'ssl_cert_reqs': ssl.CERT_NONE,
                'ssl_check_hostname': False,
                'ssl_ca_certs': None,
                'decode_responses': True
            }
        }
    ]
    
    working_config = None
    
    for test_config in configs:
        print(f"\n🧪 Testing: {test_config['name']}")
        
        try:
            r = redis.Redis(**test_config['config'])
            
            # Test ping
            result = r.ping()
            if result:
                print(f"   ✅ Ping successful!")
                
                # Test read/write
                r.set('test_key', 'test_value', ex=60)
                value = r.get('test_key')
                if value == 'test_value':
                    print(f"   ✅ Read/write successful!")
                    r.delete('test_key')
                    
                    working_config = test_config
                    print(f"   🎉 Configuration WORKS!")
                    break
                else:
                    print(f"   ❌ Read/write failed")
            else:
                print(f"   ❌ Ping failed")
                
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    return working_config

def test_alternative_connection():
    """Test using redis-cli approach"""
    
    upstash_url = os.getenv('UPSTASH_REDIS_URL')
    upstash_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
    
    print(f"\n🔧 Testing alternative connection methods...")
    
    # Extract host and port
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    if ':' in hostname:
        host, port = hostname.split(':')
        port = int(port)
    else:
        host = hostname
        port = 6379
    
    # Try with redis-cli command format
    try:
        import subprocess
        cmd = f"redis-cli -h {host} -p {port} -a {upstash_token} --tls ping"
        print(f"   Command: redis-cli -h {host} -p {port} -a {'*' * 10} --tls ping")
        
        result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and 'PONG' in result.stdout:
            print(f"   ✅ redis-cli with TLS works!")
            return True
        else:
            print(f"   ❌ redis-cli failed: {result.stderr}")
    except Exception as e:
        print(f"   ❌ redis-cli test failed: {e}")
    
    # Try without TLS
    try:
        cmd = f"redis-cli -h {host} -p {port} -a {upstash_token} ping"
        print(f"   Command: redis-cli -h {host} -p {port} -a {'*' * 10} ping")
        
        result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and 'PONG' in result.stdout:
            print(f"   ✅ redis-cli without TLS works!")
            return True
        else:
            print(f"   ❌ redis-cli without TLS failed: {result.stderr}")
    except Exception as e:
        print(f"   ❌ redis-cli without TLS test failed: {e}")
    
    return False

def generate_working_config(working_config):
    """Generate the working configuration for redis_config.py"""
    
    if not working_config:
        print(f"\n❌ No working configuration found")
        return
    
    config = working_config['config']
    
    print(f"\n📝 Working configuration found:")
    print(f"   Name: {working_config['name']}")
    print(f"   Config: {config}")
    
    # Generate the function
    config_str = str(config).replace("'", '"')
    
    function_code = f'''
def get_upstash_config(upstash_url, upstash_token):
    """Get UPSTASH specific configuration - working config for new database"""
    
    # Extract hostname and port from URL
    hostname = upstash_url.replace('https://', '').replace('http://', '')
    if ':' in hostname:
        host, port = hostname.split(':')
        port = int(port)
    else:
        host = hostname
        port = 6379
    
    return {{
        'host': host,
        'port': port,
        'password': upstash_token,
{', '.join([f"        '{k}': {repr(v)}" for k, v in config.items() if k not in ['host', 'port', 'password']])}
    }}
'''
    
    print(f"\n📋 Function to add to redis_config.py:")
    print(function_code)
    
    # Save to file
    try:
        with open('working_upstash_config.py', 'w') as f:
            f.write(function_code)
        print(f"\n✅ Saved to working_upstash_config.py")
    except Exception as e:
        print(f"\n❌ Failed to save: {e}")

if __name__ == '__main__':
    print("🚀 New UPSTASH Redis Database Test")
    print("=" * 50)
    
    # Test different configurations
    working_config = test_upstash_configs()
    
    # Test alternative methods
    cli_works = test_alternative_connection()
    
    # Generate working configuration
    if working_config:
        generate_working_config(working_config)
    
    print(f"\n📊 Summary:")
    print(f"   Python Redis: {'✅ Found working config' if working_config else '❌ No working config'}")
    print(f"   Redis CLI:    {'✅ Works' if cli_works else '❌ Failed'}")
    
    if working_config:
        print(f"\n🎉 Ready to update redis_config.py!")
    elif cli_works:
        print(f"\n⚠️  Redis-cli works but Python redis library has issues")
        print(f"💡 This might be a library version issue")
    else:
        print(f"\n❌ No working connection method found")
        print(f"💡 Check UPSTASH dashboard for connection details")