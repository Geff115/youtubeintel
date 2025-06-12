#!/bin/bash

# Simple Local Development Startup Script
echo "🚀 Starting YouTube Channel Aggregator (Simple Mode)"
echo "===================================================="

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

# Quick connection tests
echo "🔍 Testing connections..."

# Test PostgreSQL
if python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    conn.close()
    print('✅ PostgreSQL: OK')
except Exception as e:
    print(f'❌ PostgreSQL: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Database connection verified"
else
    echo "❌ Database connection failed"
    exit 1
fi

# Test Redis
if python -c "
import redis
import os
try:
    r = redis.from_url(os.getenv('REDIS_URL'))
    r.ping()
    print('✅ Redis: OK')
except Exception as e:
    print(f'❌ Redis: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Redis connection verified"
else
    echo "❌ Redis connection failed"
    exit 1
fi

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    if [ ! -z "$FLASK_PID" ] && kill -0 $FLASK_PID 2>/dev/null; then
        kill $FLASK_PID
        echo "✅ Flask app stopped"
    fi
    if [ ! -z "$CELERY_PID" ] && kill -0 $CELERY_PID 2>/dev/null; then
        kill $CELERY_PID
        echo "✅ Celery worker stopped"
    fi
    echo "👋 Goodbye!"
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Change to app directory
cd app

# Start Celery worker in background
echo "🔄 Starting Celery worker..."
celery -A tasks worker --loglevel=info --concurrency=2 > ../celery.log 2>&1 &
CELERY_PID=$!
echo "✅ Celery worker started (PID: $CELERY_PID)"

# Give Celery a moment to start
sleep 3

# Start Flask application
echo "🌐 Starting Flask application..."
python app.py > ../flask.log 2>&1 &
FLASK_PID=$!
echo "✅ Flask app started (PID: $FLASK_PID)"

# Wait for Flask to start
sleep 5

# Health check
echo "🏥 Performing health check..."
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    echo "✅ Application is healthy and ready!"
else
    echo "⚠️  Health check failed, checking logs..."
    echo "Flask logs:"
    tail -10 ../flask.log
    echo "Celery logs:"
    tail -10 ../celery.log
fi

echo ""
echo "🎉 Services are running!"
echo "======================="
echo ""
echo "🌐 Available endpoints:"
echo "   Health:     http://localhost:5000/health"
echo "   Stats:      http://localhost:5000/api/stats"
echo "   API Keys:   http://localhost:5000/api/api-keys"
echo "   Jobs:       http://localhost:5000/api/jobs"
echo ""
echo "📊 Service Status:"
echo "   Flask App:      Running (PID: $FLASK_PID)"
echo "   Celery Worker:  Running (PID: $CELERY_PID)"
echo ""
echo "📝 Log files:"
echo "   Flask:  flask.log"
echo "   Celery: celery.log"
echo ""
echo "🔧 Quick test commands:"
echo "   # Check stats"
echo "   curl http://localhost:5000/api/stats"
echo ""
echo "   # List API keys"
echo "   curl http://localhost:5000/api/api-keys"
echo ""
echo "   # Fetch metadata for sample channels"
echo "   curl -X POST http://localhost:5000/api/fetch-metadata \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"limit\": 3}'"
echo ""
echo "💡 Press Ctrl+C to stop all services"
echo ""

# Wait for user to stop the services
wait