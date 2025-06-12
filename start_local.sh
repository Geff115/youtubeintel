#!/bin/bash

# Local Development Startup Script
echo "🚀 Starting YouTube Channel Aggregator (Local Mode)"
echo "=================================================="

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
    echo "💡 Run ./local_setup.sh first"
    exit 1
fi

# Check if API keys are configured
if [[ "$YOUTUBE_API_KEY_1" == "your-youtube-api-key-1" ]] || [[ -z "$YOUTUBE_API_KEY_1" ]]; then
    echo "⚠️  YouTube API keys not configured in .env file"
    echo "💡 Please edit .env file with your actual YouTube API keys"
    exit 1
fi

# Check PostgreSQL connection
echo "🔍 Checking PostgreSQL connection..."
if python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    conn.close()
    print('✅ PostgreSQL connection successful')
except Exception as e:
    print(f'❌ PostgreSQL connection failed: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Database connection verified"
else
    echo "❌ Database connection failed"
    echo "💡 Make sure PostgreSQL is running and database is set up"
    echo "   Run ./local_setup.sh to set up the database"
    exit 1
fi

# Check Redis connection
echo "🔍 Checking Redis connection..."
if python -c "
import redis
import os
try:
    r = redis.from_url(os.getenv('REDIS_URL'))
    r.ping()
    print('✅ Redis connection successful')
except Exception as e:
    print(f'❌ Redis connection failed: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Redis connection verified"
else
    echo "❌ Redis connection failed"
    echo "💡 Make sure Redis is running:"
    echo "   redis-server  # Start Redis server"
    exit 1
fi

# Initialize system if needed
echo "🔧 Initializing system..."
cd app
if python setup.py; then
    echo "✅ System initialization completed"
else
    echo "❌ System initialization failed"
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
    if [ ! -z "$BEAT_PID" ] && kill -0 $BEAT_PID 2>/dev/null; then
        kill $BEAT_PID
        echo "✅ Celery beat stopped"
    fi
    echo "👋 Goodbye!"
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Start Celery worker in background
echo "🔄 Starting Celery worker..."
celery -A tasks worker --loglevel=info --concurrency=2 &
CELERY_PID=$!
echo "✅ Celery worker started (PID: $CELERY_PID)"

# Start Celery beat in background
echo "⏰ Starting Celery beat scheduler..."
celery -A tasks beat --loglevel=info &
BEAT_PID=$!
echo "✅ Celery beat started (PID: $BEAT_PID)"

# Give Celery a moment to start
sleep 3

# Start Flask application
echo "🌐 Starting Flask application..."
python app.py &
FLASK_PID=$!
echo "✅ Flask app started (PID: $FLASK_PID)"

# Wait for Flask to start
sleep 5

# Health check
echo "🏥 Performing health check..."
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    echo "✅ Application is healthy and ready!"
else
    echo "⚠️  Health check failed, but services are running"
    echo "💡 Check if Flask app started correctly"
fi

echo ""
echo "🎉 All services are running!"
echo "============================"
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
echo "   Celery Beat:    Running (PID: $BEAT_PID)"
echo ""
echo "🔧 Quick test commands:"
echo "   # Check stats"
echo "   curl http://localhost:5000/api/stats"
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