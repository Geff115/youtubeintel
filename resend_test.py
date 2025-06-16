"""
Quick test script for Resend API
Run this to verify your Resend API key works before setting up the full authentication system
"""

import os
import requests
from dotenv import load_dotenv

def test_resend_api():
    """Test Resend API with your API key"""
    load_dotenv()
    
    # Get API key from environment
    api_key = os.getenv('RESEND_API_KEY')
    test_email = os.getenv('TEST_EMAIL')  # Add your email to test with
    
    if not api_key:
        print("❌ RESEND_API_KEY not found in environment variables")
        print("💡 Add RESEND_API_KEY=your-api-key to your .env file")
        return False
    
    if not test_email:
        print("⚠️  No TEST_EMAIL specified")
        test_email = input("Enter your email address to test with: ").strip()
        if not test_email:
            print("❌ No email provided")
            return False
    
    print(f"🧪 Testing Resend API with key: {api_key[:8]}...")
    print(f"📧 Sending test email to: {test_email}")
    
    # Prepare test email
    email_data = {
        "from": "YouTubeIntel <notifications@youtubeintel.com>",  # We may need to verify this domain
        "to": [test_email],
        "subject": "🎉 YouTubeIntel Email Test - Success!",
        "html": """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
                .container { max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center; }
                .logo { color: white; font-size: 28px; font-weight: bold; margin: 0; }
                .content { padding: 40px 30px; }
                .success { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 5px; color: #155724; margin-bottom: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 class="logo">YouTubeIntel</h1>
                </div>
                <div class="content">
                    <div class="success">
                        <strong>✅ Email Service Test Successful!</strong>
                    </div>
                    <h2>Resend Integration Working!</h2>
                    <p>Congratulations! Your Resend API key is working correctly.</p>
                    <p>This means your YouTubeIntel authentication system will be able to send:</p>
                    <ul>
                        <li>📧 Email verification messages</li>
                        <li>🔑 Password reset instructions</li>
                        <li>🎉 Welcome emails</li>
                        <li>📊 Usage notifications</li>
                    </ul>
                    <p>You're ready to proceed with the authentication setup!</p>
                </div>
            </div>
        </body>
        </html>
        """,
        "text": """
        YouTubeIntel Email Test - Success!
        
        ✅ Email Service Test Successful!
        
        Congratulations! Your Resend API key is working correctly.
        
        This means your YouTubeIntel authentication system will be able to send:
        - Email verification messages
        - Password reset instructions
        - Welcome emails
        - Usage notifications
        
        You're ready to proceed with the authentication setup!
        """
    }
    
    # Send via Resend API
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=email_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            email_id = result.get('id', 'unknown')
            
            print("🎉 SUCCESS! Test email sent successfully!")
            print(f"📬 Email ID: {email_id}")
            print(f"📧 Check your inbox at: {test_email}")
            print("")
            print("✅ Your Resend API key is working correctly!")
            print("✅ You can now proceed with the full authentication setup.")
            return True
            
        else:
            print(f"❌ Resend API Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"📋 Error details: {error_data}")
                
                # Common error solutions
                if response.status_code == 422:
                    print("\n💡 Common solutions for 422 errors:")
                    print("   - Verify your 'from' domain in Resend dashboard")
                    print("   - Use a verified sender email address")
                    print("   - Check if your domain DNS is properly configured")
                elif response.status_code == 401:
                    print("\n💡 Authentication error:")
                    print("   - Check your RESEND_API_KEY is correct")
                    print("   - Make sure there are no extra spaces in the API key")
                
            except:
                print(f"📋 Raw response: {response.text}")
            
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
        print("\n💡 Possible solutions:")
        print("   - Check your internet connection")
        print("   - Verify the API key is correct")
        print("   - Try again in a few minutes")
        return False

def main():
    print("🧪 Resend API Test for YouTubeIntel")
    print("=" * 40)
    
    success = test_resend_api()
    
    if success:
        print("\n🚀 Next Steps:")
        print("1. Run the authentication setup: python auth_setup.py")
        print("2. Update your .env with RESEND_API_KEY")
        print("3. Set up your frontend authentication")
        print("4. Launch your service!")
    else:
        print("\n🔧 Troubleshooting:")
        print("1. Double-check your RESEND_API_KEY in .env")
        print("2. Verify your domain in Resend dashboard")
        print("3. Check Resend documentation: https://resend.com/docs")
        print("4. Contact Resend support if needed")

if __name__ == '__main__':
    main()