#!/bin/bash

# Production Startup Script for YouTube Channel Aggregator
echo "🚀 Starting YouTube Channel Aggregator (Production Mode)"
echo "======================================================="

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

# Set environment to production if not already set
export ENVIRONMENT=${ENVIRONMENT:-production}
echo "🌍 Environment: $ENVIRONMENT"

# Check required environment variables
required_vars=("DATABASE_URL" "SECRET_KEY" "YOUTUBE_API_KEY_1")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Missing required environment variables:"
    printf '   %s\n' "${missing_vars[@]}"
    exit 1
fi

# Determine Redis configuration
if [ "$ENVIRONMENT" = "production" ] && [ -n "$UPSTASH_REDIS_URL" ] && [ -n "$UPSTASH_REDIS_REST_TOKEN" ]; then
    echo "🌐 Using UPSTASH Redis for production"
    REDIS_TYPE="UPSTASH"
elif [ -n "$REDIS_URL" ]; then
    echo "🏠 Using local/custom Redis"
    REDIS_TYPE="LOCAL"
else
    echo "❌ No Redis configuration found"
    echo "💡 Set either UPSTASH_REDIS_URL + UPSTASH_REDIS_REST_TOKEN or REDIS_URL"
    exit 1
fi

# Test connections
echo "🔍 Testing connections..."

# Test database connection
if python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    conn.close()
    print('✅ Database: Connected')
except Exception as e:
    print(f'❌ Database: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Database connection verified"
else
    echo "❌ Database connection failed"
    exit 1
fi

# Test Redis connection
cd app
if python -c "
from redis_config import test_redis_connection
try:
    result = test_redis_connection()
    if result['status'] == 'success':
        print('✅ Redis: Connected')
        print(f'   Type: $REDIS_TYPE')
        print(f\"   Version: {result.get('redis_version', 'unknown')}\")
        print(f\"   Environment: {result.get('environment', 'unknown')}\")
    else:
        print(f'❌ Redis: {result.get(\"message\", \"Connection failed\")}')
        exit(1)
except Exception as e:
    print(f'❌ Redis: {e}')
    exit(1)
" 2>/dev/null; then
    echo "✅ Redis connection verified"
else
    echo "❌ Redis connection failed"
    exit 1
fi

cd ..

# Get configuration values
CELERY_CONCURRENCY=${CELERY_CONCURRENCY:-4}
API_RATE_LIMIT_DELAY=${API_RATE_LIMIT_DELAY:-0.1}

echo ""
echo "⚙️  Configuration:"
echo "   Environment: $ENVIRONMENT"
echo "   Redis Type: $REDIS_TYPE"
echo "   Celery Concurrency: $CELERY_CONCURRENCY"
echo "   API Rate Limit: ${API_RATE_LIMIT_DELAY}s"
echo "   Database: $(echo $DATABASE_URL | sed 's/:[^@]*@/:***@/')"

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    if [ ! -z "$FLASK_PID" ] && kill -0 $FLASK_PID 2>/dev/null; then
        kill $FLASK_PID
        echo "✅ Flask app stopped"
    fi
    if [ ! -z "$CELERY_WORKER_PID" ] && kill -0 $CELERY_WORKER_PID 2>/dev/null; then
        kill $CELERY_WORKER_PID
        echo "✅ Celery worker stopped"
    fi
    if [ ! -z "$CELERY_BEAT_PID" ] && kill -0 $CELERY_BEAT_PID 2>/dev/null; then
        kill $CELERY_BEAT_PID
        echo "✅ Celery beat stopped"
    fi
    echo "👋 Production services stopped"
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Change to app directory
cd app

echo ""
echo "🚀 Starting production services..."

# Start Celery worker with production settings
echo "🔄 Starting Celery worker..."
celery -A tasks worker \
    --loglevel=info \
    --concurrency=$CELERY_CONCURRENCY \
    --queues=migration,youtube_api,discovery,batch_processing \
    --prefetch-multiplier=1 \
    --max-tasks-per-child=1000 \
    --time-limit=3600 \
    --soft-time-limit=3300 \
    > ../celery_worker.log 2>&1 &
CELERY_WORKER_PID=$!
echo "✅ Celery worker started (PID: $CELERY_WORKER_PID)"

# Start Celery beat scheduler
echo "⏰ Starting Celery beat scheduler..."
celery -A tasks beat \
    --loglevel=info \
    --schedule=/tmp/celerybeat-schedule \
    --pidfile=/tmp/celerybeat.pid \
    > ../celery_beat.log 2>&1 &
CELERY_BEAT_PID=$!
echo "✅ Celery beat started (PID: $CELERY_BEAT_PID)"

# Give Celery services time to start
sleep 5

# Start Flask application in production mode
echo "🌐 Starting Flask application..."
if [ "$ENVIRONMENT" = "production" ]; then
    # Use Gunicorn for production
    if command -v gunicorn &> /dev/null; then
        gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --keep-alive 2 app:app > ../flask.log 2>&1 &
        FLASK_PID=$!
        echo "✅ Flask app started with Gunicorn (PID: $FLASK_PID)"
    else
        python app.py > ../flask.log 2>&1 &
        FLASK_PID=$!
        echo "✅ Flask app started with development server (PID: $FLASK_PID)"
        echo "⚠️  Consider installing Gunicorn for production: pip install gunicorn"
    fi
else
    python app.py > ../flask.log 2>&1 &
    FLASK_PID=$!
    echo "✅ Flask app started (PID: $FLASK_PID)"
fi

# Wait for Flask to start
sleep 8

# Health check
echo "🏥 Performing health check..."
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    echo "✅ Application is healthy and ready!"
    
    # Test system status endpoint
    if curl -f http://localhost:5000/api/system-status > /dev/null 2>&1; then
        echo "✅ System status endpoint responding"
    fi
    
    # Test Redis endpoint
    if curl -f http://localhost:5000/api/redis-test > /dev/null 2>&1; then
        echo "✅ Redis test endpoint responding"
    fi
    
else
    echo "⚠️  Health check failed, checking logs..."
    echo ""
    echo "Flask logs (last 10 lines):"
    tail -10 ../flask.log
    echo ""
    echo "Celery worker logs (last 10 lines):"
    tail -10 ../celery_worker.log
fi

echo ""
echo "🎉 Production services are running!"
echo "==================================="
echo ""
echo "🌐 Application URLs:"
echo "   Health Check:    http://localhost:5000/health"
echo "   System Status:   http://localhost:5000/api/system-status"
echo "   Redis Test:      http://localhost:5000/api/redis-test"
echo "   Worker Status:   http://localhost:5000/api/worker-status"
echo "   API Stats:       http://localhost:5000/api/stats"
echo ""
echo "📊 Service Status:"
echo "   Flask App:       Running (PID: $FLASK_PID)"
echo "   Celery Worker:   Running (PID: $CELERY_WORKER_PID)"
echo "   Celery Beat:     Running (PID: $CELERY_BEAT_PID)"
echo "   Redis Type:      $REDIS_TYPE"
echo "   Environment:     $ENVIRONMENT"
echo ""
echo "📝 Log files:"
echo "   Flask:           flask.log"
echo "   Celery Worker:   celery_worker.log"
echo "   Celery Beat:     celery_beat.log"
echo ""
echo "🚀 High-Volume Processing Commands:"
echo "   # Process metadata for millions of channels"
echo "   curl -X POST http://localhost:5000/api/batch-metadata \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"batch_size\": 5000, \"total_limit\": 100000}'"
echo ""
echo "   # Process videos for channels with metadata"
echo "   curl -X POST http://localhost:5000/api/batch-videos \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"batch_size\": 1000}'"
echo ""
echo "   # Discover related channels"
echo "   curl -X POST http://localhost:5000/api/batch-discovery \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"batch_size\": 500}'"
echo ""
echo "   # Migrate from existing data source"
echo "   curl -X POST http://localhost:5000/api/migrate \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"source_type\": \"csv\", \"source_path\": \"/path/to/channels.csv\", \"batch_size\": 10000}'"
echo ""
echo "💡 Press Ctrl+C to stop all services"
echo ""

# Wait for user to stop the services
wait