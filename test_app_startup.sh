#!/bin/bash

# Test App Startup Script
echo "🚀 Testing YouTubeIntel App Startup"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "app/app.py" ]; then
    echo "❌ app/app.py not found. Make sure you're in the project root directory."
    exit 1
fi

# Check if virtual environment is active
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  No virtual environment detected"
    echo "💡 Activate your virtual environment first:"
    echo "   source venv/bin/activate"
    exit 1
fi

# Load environment variables
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env"
    export $(grep -v '^#' .env | xargs)
else
    echo "❌ .env file not found"
    exit 1
fi

echo "🧪 Testing app startup..."

# Change to app directory and test imports
cd app

# Test basic imports
python3 -c "
import sys
import os
print('Testing imports...')

try:
    from database import db
    print('✅ Database module imported')
    
    from models import User, Channel
    print('✅ Models imported')
    
    from auth import auth_service
    print('✅ Auth service imported')
    
    from rate_limiter import rate_limiter  
    print('✅ Rate limiter imported')
    
    from email_service import EmailService
    print('✅ Email service imported')
    
    print('✅ All core modules imported successfully!')
    
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo "✅ Import test passed!"
    echo ""
    echo "🚀 Starting Flask app..."
    echo "   Press Ctrl+C to stop"
    echo ""
    
    # Start the app
    python3 app.py
else
    echo "❌ Import test failed"
    exit 1
fi