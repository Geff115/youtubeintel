#!/usr/bin/env python3
"""
Temporarily bypass UPSTASH and use local Redis for testing
"""

import os

def create_local_env():
    """Create a .env file that forces local Redis usage"""
    
    print("🔧 Creating local Redis configuration...")
    
    # Read current .env
    env_lines = []
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            env_lines = f.readlines()
    
    # Modify environment to use local Redis
    new_env_lines = []
    found_environment = False
    found_upstash_url = False
    found_upstash_token = False
    
    for line in env_lines:
        if line.startswith('ENVIRONMENT='):
            new_env_lines.append('ENVIRONMENT=development\n')
            found_environment = True
        elif line.startswith('UPSTASH_REDIS_URL='):
            new_env_lines.append('# UPSTASH_REDIS_URL=your_upstash_redis_url_here\n')
            found_upstash_url = True
        elif line.startswith('UPSTASH_REDIS_REST_TOKEN='):
            new_env_lines.append('# UPSTASH_REDIS_REST_TOKEN=your_upstash_redis_rest_token_here\n')
            found_upstash_token = True
        elif line.startswith('REDIS_URL='):
            new_env_lines.append('REDIS_URL=redis://localhost:6379/0\n')
        else:
            new_env_lines.append(line)
    
    # Add missing variables
    if not found_environment:
        new_env_lines.append('ENVIRONMENT=development\n')
    if not found_upstash_url:
        new_env_lines.append('# UPSTASH_REDIS_URL=your_upstash_redis_url_here\n')
    if not found_upstash_token:
        new_env_lines.append('# UPSTASH_REDIS_REST_TOKEN=your_upstash_redis_rest_token_here\n')
    
    # Write back to .env
    with open('.env', 'w') as f:
        f.writelines(new_env_lines)
    
    print("✅ Updated .env to use local Redis")
    print("✅ Environment set to 'development'")
    print("✅ UPSTASH credentials commented out")

def create_production_env():
    """Create a .env file that uses UPSTASH Redis"""
    
    print("🔧 Creating UPSTASH Redis configuration...")
    
    # Read current .env
    env_lines = []
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            env_lines = f.readlines()
    
    # Modify environment to use UPSTASH Redis
    new_env_lines = []
    
    for line in env_lines:
        if line.startswith('ENVIRONMENT='):
            new_env_lines.append('ENVIRONMENT=production\n')
        elif line.startswith('# UPSTASH_REDIS_URL='):
            # Uncomment UPSTASH URL (user needs to set actual value)
            new_env_lines.append('UPSTASH_REDIS_URL=your_actual_upstash_redis_url_here\n')
        elif line.startswith('# UPSTASH_REDIS_REST_TOKEN='):
            # Uncomment UPSTASH token (user needs to set actual value)
            new_env_lines.append('UPSTASH_REDIS_REST_TOKEN=your_actual_upstash_redis_rest_token_here\n')
        else:
            new_env_lines.append(line)
    
    # Write back to .env
    with open('.env', 'w') as f:
        f.writelines(new_env_lines)
    
    print("✅ Updated .env for UPSTASH Redis")
    print("⚠️  Please set your actual UPSTASH credentials in .env")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'production':
        create_production_env()
        print("\n💡 Next steps:")
        print("1. Edit .env with your actual UPSTASH credentials")
        print("2. Run: ./start_production.sh")
    else:
        create_local_env()
        print("\n💡 Next steps:")
        print("1. Make sure Redis is running: redis-server --daemonize yes")
        print("2. Run: ./start_production.sh")
        print("3. Test: curl http://localhost:5000/api/redis-test")