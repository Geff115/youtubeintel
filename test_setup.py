#!/usr/bin/env python3
"""
Test script to verify local setup is working
"""

import os
import sys
from dotenv import load_dotenv

def test_imports():
    """Test if all required packages can be imported"""
    print("🧪 Testing Python imports...")
    
    try:
        import flask
        print("✅ Flask imported successfully")
    except ImportError as e:
        print(f"❌ Flask import failed: {e}")
        return False
    
    try:
        import psycopg2
        print("✅ psycopg2 imported successfully")
    except ImportError as e:
        print(f"❌ psycopg2 import failed: {e}")
        return False
    
    try:
        import redis
        print("✅ Redis imported successfully")
    except ImportError as e:
        print(f"❌ Redis import failed: {e}")
        return False
    
    try:
        import celery
        print("✅ Celery imported successfully")
    except ImportError as e:
        print(f"❌ Celery import failed: {e}")
        return False
    
    try:
        from googleapiclient.discovery import build
        print("✅ Google API client imported successfully")
    except ImportError as e:
        print(f"❌ Google API client import failed: {e}")
        return False
    
    return True

def test_database():
    """Test database connection"""
    print("\n🗄️  Testing database connection...")
    
    try:
        import psycopg2
        
        # Load environment variables
        load_dotenv()
        db_url = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost:5432/youtube_channels')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Database connection successful")
        print(f"   PostgreSQL version: {version.split()[0]} {version.split()[1]}")
        
        # Test tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['channels', 'videos', 'api_keys', 'processing_jobs', 'channel_discoveries']
        missing_tables = [table for table in expected_tables if table not in tables]
        
        if missing_tables:
            print(f"⚠️  Missing tables: {missing_tables}")
        else:
            print("✅ All required tables exist")
        
        # Test sample data
        cursor.execute("SELECT COUNT(*) FROM channels;")
        channel_count = cursor.fetchone()[0]
        print(f"✅ Found {channel_count} channels in database")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_redis():
    """Test Redis connection"""
    print("\n🔴 Testing Redis connection...")
    
    try:
        import redis
        
        load_dotenv()
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        
        r = redis.from_url(redis_url)
        
        # Test ping
        response = r.ping()
        if response:
            print("✅ Redis connection successful")
            
            # Test basic operations
            r.set('test_key', 'test_value')
            value = r.get('test_key')
            if value == b'test_value':
                print("✅ Redis read/write operations working")
                r.delete('test_key')
            else:
                print("⚠️  Redis read/write test failed")
            
            return True
        else:
            print("❌ Redis ping failed")
            return False
            
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_environment():
    """Test environment configuration"""
    print("\n🌍 Testing environment configuration...")
    
    load_dotenv()
    
    # Check required environment variables
    required_vars = ['DATABASE_URL', 'REDIS_URL', 'SECRET_KEY']
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var} is set")
        else:
            print(f"❌ {var} is missing")
            missing_vars.append(var)
    
    # Check YouTube API keys
    api_keys = []
    for i in range(1, 6):
        key = os.getenv(f'YOUTUBE_API_KEY_{i}')
        if key and key != f'your-youtube-api-key-{i}':
            api_keys.append(key)
    
    if api_keys:
        print(f"✅ Found {len(api_keys)} YouTube API key(s)")
    else:
        print("⚠️  No YouTube API keys configured")
        print("   Please edit .env file with your actual API keys")
    
    return len(missing_vars) == 0

def test_app_structure():
    """Test if app files are in the right place"""
    print("\n📁 Testing application structure...")
    
    required_files = [
        'app/app.py',
        'app/models.py',
        'app/tasks.py',
        'app/youtube_service.py',
        'app/external_services.py',
        '.env',
        'requirements.txt'
    ]
    
    missing_files = []
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
            missing_files.append(file_path)
    
    return len(missing_files) == 0

def main():
    """Run all tests"""
    print("🧪 YouTube Channel Aggregator - Setup Test")
    print("==========================================")
    
    tests = [
        ("Python Imports", test_imports),
        ("Environment Config", test_environment),
        ("App Structure", test_app_structure),
        ("Database Connection", test_database),
        ("Redis Connection", test_redis)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    print("\n📊 Test Results Summary:")
    print("========================")
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
        if not passed:
            all_passed = False
    
    print(f"\n🎯 Overall Status: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n🚀 Your system is ready!")
        print("Next steps:")
        print("1. Make sure your YouTube API keys are in .env")
        print("2. Run: cd app && python setup.py")
        print("3. Start the app: ./start_local.sh")
    else:
        print("\n🔧 Please fix the failed tests before proceeding")
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())