#!/usr/bin/env python3
"""
Quick test to verify authentication setup is working
Run this after the auth setup to test everything
"""

import os
import sys
import requests
import json
from datetime import datetime

# Add app directory to path
sys.path.insert(0, os.path.join(os.getcwd(), 'app'))

def test_app_startup():
    """Test that the app can start up with authentication"""
    print("🚀 Testing app startup with authentication...")
    
    try:
        # Import the main modules
        from app.auth import auth_service
        from app.models import User
        from app.database import db
        
        print("  ✅ Core modules imported successfully")
        
        # Test JWT functionality
        token = auth_service.generate_jwt_token('test-123', 'test@test.com')
        payload = auth_service.verify_jwt_token(token)
        assert payload['user_id'] == 'test-123'
        print("  ✅ JWT token system works")
        
        # Test password hashing
        password = "TestPassword123!"
        hashed = auth_service.hash_password(password)
        assert auth_service.verify_password(password, hashed)
        print("  ✅ Password hashing works")
        
        print("✅ App startup test passed!")
        return True
        
    except Exception as e:
        print(f"❌ App startup test failed: {e}")
        return False

def test_api_endpoints():
    """Test API endpoints if app is running"""
    print("🌐 Testing API endpoints...")
    
    base_url = "http://localhost:5000"
    
    try:
        # Test health endpoint
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"  ✅ Health endpoint: {health_data.get('status', 'unknown')}")
            
            # Check if authentication features are enabled
            features = health_data.get('features', {})
            auth_enabled = features.get('authentication', False)
            if auth_enabled:
                print("  ✅ Authentication features enabled")
            else:
                print("  ⚠️  Authentication features not enabled")
        else:
            print(f"  ❌ Health endpoint failed: {response.status_code}")
            return False
        
        # Test signup endpoint (should require data but not crash)
        response = requests.post(f"{base_url}/api/auth/signup", 
                               json={}, 
                               timeout=5)
        if response.status_code == 400:  # Expected - missing data
            print("  ✅ Signup endpoint responding (validation working)")
        else:
            print(f"  ⚠️  Signup endpoint unexpected response: {response.status_code}")
        
        print("✅ API endpoint tests passed!")
        return True
        
    except requests.exceptions.ConnectionError:
        print("  ℹ️  App not running - start with: python app/app.py")
        return False
    except Exception as e:
        print(f"  ❌ API test failed: {e}")
        return False

def test_database_setup():
    """Test database tables are created"""
    print("🗄️  Testing database setup...")
    
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        
        load_dotenv()
        DATABASE_URL = os.getenv('DATABASE_URL')
        
        engine = create_engine(DATABASE_URL)
        
        # Check if authentication tables exist
        with engine.connect() as conn:
            # Check users table
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'auth_method'
            """))
            if result.fetchone():
                print("  ✅ Users table has authentication fields")
            else:
                print("  ❌ Users table missing authentication fields")
                return False
            
            # Check user_sessions table
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_name = 'user_sessions'
            """))
            if result.fetchone():
                print("  ✅ User sessions table exists")
            else:
                print("  ❌ User sessions table missing")
                return False
            
            # Check api_usage_logs table
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_name = 'api_usage_logs'
            """))
            if result.fetchone():
                print("  ✅ API usage logs table exists")
            else:
                print("  ❌ API usage logs table missing")
                return False
        
        print("✅ Database setup verified!")
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def main():
    """Run all authentication tests"""
    print("🧪 YouTubeIntel Authentication Verification")
    print("=" * 50)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("App Startup", test_app_startup),
        ("Database Setup", test_database_setup),
        ("API Endpoints", test_api_endpoints),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        if test_func():
            passed += 1
        print()
    
    print("📊 Test Summary")
    print("=" * 30)
    print(f"✅ Passed: {passed}/{total} tests")
    
    if passed == total:
        print("\n🎉 All tests passed! Your authentication system is ready!")
        print("\n📋 Next Steps:")
        print("1. Start the app: python app/app.py")
        print("2. Test signup: curl -X POST http://localhost:5000/api/auth/signup \\")
        print("   -H 'Content-Type: application/json' \\")
        print("   -d '{\"email\":\"test@test.com\",\"password\":\"Test123!\",\"first_name\":\"Test\",\"last_name\":\"User\",\"age_confirmed\":true,\"agreed_to_terms\":true}'")
        print("3. Build your React frontend!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the errors above.")
        print("💡 Try running auth_setup.py again to fix issues.")
    
    print(f"\n🕐 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()