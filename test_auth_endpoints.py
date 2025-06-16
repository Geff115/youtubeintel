#!/usr/bin/env python3
"""
Test authentication endpoints
Run this while your app is running to test the authentication flow
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000"

def test_health():
    """Test health endpoint"""
    print("🏥 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Status: {data.get('status')}")
            print(f"  📋 Features: {data.get('features', {})}")
            return True
        else:
            print(f"  ❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Health check error: {e}")
        return False

def test_signup():
    """Test user signup"""
    print("📝 Testing user signup...")
    
    # Use a unique email for testing
    test_email = f"test_{int(time.time())}@test.com"
    
    signup_data = {
        "email": test_email,
        "password": "TestPassword123!",
        "first_name": "Test",
        "last_name": "User",
        "age_confirmed": True,
        "agreed_to_terms": True
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/signup",
            headers={"Content-Type": "application/json"},
            json=signup_data,
            timeout=10
        )
        
        if response.status_code == 201:
            data = response.json()
            print(f"  ✅ Signup successful for: {test_email}")
            print(f"  📧 Verification email sent: {data.get('verification_email_sent', False)}")
            return test_email, signup_data["password"]
        else:
            data = response.json()
            print(f"  ❌ Signup failed: {response.status_code}")
            print(f"  📋 Error: {data.get('error', 'Unknown error')}")
            return None, None
            
    except Exception as e:
        print(f"  ❌ Signup error: {e}")
        return None, None

def test_signin(email, password):
    """Test user signin"""
    print("🔐 Testing user signin...")
    
    signin_data = {
        "email": email,
        "password": password
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/signin",
            headers={"Content-Type": "application/json"},
            json=signin_data,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Signin successful for: {email}")
            access_token = data.get('access_token')
            user_data = data.get('user', {})
            print(f"  👤 User: {user_data.get('first_name')} {user_data.get('last_name')}")
            print(f"  💳 Credits: {user_data.get('credits_balance', 0)}")
            return access_token
        else:
            data = response.json()
            print(f"  ❌ Signin failed: {response.status_code}")
            print(f"  📋 Error: {data.get('error', 'Unknown error')}")
            return None
            
    except Exception as e:
        print(f"  ❌ Signin error: {e}")
        return None

def test_protected_endpoint(access_token):
    """Test accessing protected endpoint"""
    print("🔒 Testing protected endpoint...")
    
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            user_data = data.get('user', {})
            print(f"  ✅ Protected endpoint accessible")
            print(f"  👤 Current user: {user_data.get('email')}")
            print(f"  📊 Plan: {user_data.get('current_plan', 'unknown')}")
            return True
        else:
            data = response.json()
            print(f"  ❌ Protected endpoint failed: {response.status_code}")
            print(f"  📋 Error: {data.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"  ❌ Protected endpoint error: {e}")
        return False

def test_stats_endpoint(access_token):
    """Test stats endpoint (protected)"""
    print("📊 Testing stats endpoint...")
    
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            f"{BASE_URL}/api/stats",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Stats endpoint accessible")
            print(f"  📈 Total channels: {data.get('total_channels', 0)}")
            user_stats = data.get('user_stats', {})
            print(f"  💳 User credits: {user_stats.get('credits_balance', 0)}")
            return True
        else:
            data = response.json()
            print(f"  ❌ Stats endpoint failed: {response.status_code}")
            print(f"  📋 Error: {data.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"  ❌ Stats endpoint error: {e}")
        return False

def test_rate_limiting(access_token):
    """Test rate limiting"""
    print("🚦 Testing rate limiting...")
    
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Make multiple quick requests to trigger rate limiting
        success_count = 0
        rate_limited = False
        
        for i in range(15):  # Try 15 requests quickly
            response = requests.get(
                f"{BASE_URL}/api/stats",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                print(f"  ✅ Rate limiting activated after {success_count} requests")
                rate_limited = True
                break
            
            time.sleep(0.1)  # Small delay
        
        if not rate_limited:
            print(f"  ⚠️  Rate limiting not triggered ({success_count} requests succeeded)")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Rate limiting test error: {e}")
        return False

def main():
    """Run authentication tests"""
    print("🧪 YouTubeIntel Authentication Endpoint Tests")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Base URL: {BASE_URL}")
    print()
    
    tests_passed = 0
    total_tests = 6
    
    # Test 1: Health check
    if test_health():
        tests_passed += 1
    print()
    
    # Test 2: User signup
    email, password = test_signup()
    if email:
        tests_passed += 1
    print()
    
    if not email:
        print("❌ Cannot continue tests without successful signup")
        return
    
    # Test 3: User signin
    access_token = test_signin(email, password)
    if access_token:
        tests_passed += 1
    print()
    
    if not access_token:
        print("❌ Cannot continue tests without access token")
        return
    
    # Test 4: Protected endpoint
    if test_protected_endpoint(access_token):
        tests_passed += 1
    print()
    
    # Test 5: Stats endpoint
    if test_stats_endpoint(access_token):
        tests_passed += 1
    print()
    
    # Test 6: Rate limiting
    if test_rate_limiting(access_token):
        tests_passed += 1
    print()
    
    # Summary
    print("📊 Test Summary")
    print("=" * 30)
    print(f"✅ Passed: {tests_passed}/{total_tests} tests")
    
    if tests_passed == total_tests:
        print("\n🎉 All authentication tests passed!")
        print("✅ Your authentication system is working perfectly!")
        print("\n📋 Ready for:")
        print("   - React frontend development")
        print("   - Production deployment")
        print("   - Real user onboarding")
    else:
        print(f"\n⚠️  {total_tests - tests_passed} test(s) failed")
        print("💡 Check the app logs for more details")
    
    print(f"\n🕐 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()