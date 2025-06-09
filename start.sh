#!/bin/bash

# YouTube Channel Data Aggregation System - Startup Script
echo "🚀 Starting YouTube Channel Data Aggregation System"
echo "=================================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found"
    echo "📝 Creating .env from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file"
        echo "⚠️  Please edit .env file with your YouTube API keys before continuing"
        echo "   Required: YOUTUBE_API_KEY_1, YOUTUBE_API_KEY_2, SECRET_KEY"
        exit 1
    else
        echo "❌ .env.example not found"
        exit 1
    fi
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "🐳 Docker is running"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    if ! command -v docker &> /dev/null; then
        echo "❌ Neither docker-compose nor docker compose is available"
        exit 1
    else
        COMPOSE_CMD="docker compose"
    fi
else
    COMPOSE_CMD="docker-compose"
fi

echo "🔧 Using: $COMPOSE_CMD"

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
$COMPOSE_CMD down

# Pull latest images
echo "📥 Pulling latest images..."
$COMPOSE_CMD pull

# Build the application
echo "🏗️  Building application..."
$COMPOSE_CMD build

# Start the services
echo "🚀 Starting services..."
$COMPOSE_CMD up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check service status
echo "📊 Checking service status..."
$COMPOSE_CMD ps

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if $COMPOSE_CMD exec -T db pg_isready -U youtube > /dev/null 2>&1; then
        echo "✅ Database is ready"
        break
    fi
    
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ Database failed to start after $max_attempts attempts"
        echo "🔍 Database logs:"
        $COMPOSE_CMD logs db
        exit 1
    fi
    
    echo "   Attempt $attempt/$max_attempts - waiting..."
    sleep 2
    ((attempt++))
done

# Wait for Redis to be ready
echo "⏳ Waiting for Redis to be ready..."
attempt=1
while [ $attempt -le $max_attempts ]; do
    if $COMPOSE_CMD exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis is ready"
        break
    fi
    
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ Redis failed to start after $max_attempts attempts"
        echo "🔍 Redis logs:"
        $COMPOSE_CMD logs redis
        exit 1
    fi
    
    echo "   Attempt $attempt/$max_attempts - waiting..."
    sleep 2
    ((attempt++))
done

# Initialize the system
echo "🔧 Initializing system..."
if $COMPOSE_CMD exec -T app python setup.py; then
    echo "✅ System initialized successfully"
else
    echo "❌ System initialization failed"
    echo "🔍 Application logs:"
    $COMPOSE_CMD logs app
    exit 1
fi

# Health check
echo "🏥 Performing health check..."
sleep 5

# Check if the application is responding
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    echo "✅ Application is healthy"
else
    echo "⚠️  Application health check failed, but services are running"
    echo "🔍 Check logs with: $COMPOSE_CMD logs app"
fi

echo ""
echo "🎉 System startup completed!"
echo "================================"
echo ""
echo "📊 Service Status:"
$COMPOSE_CMD ps
echo ""
echo "🌐 Available Endpoints:"
echo "   Health Check: http://localhost:5000/health"
echo "   System Stats: http://localhost:5000/api/stats"
echo "   API Keys:     http://localhost:5000/api/api-keys"
echo "   Jobs:         http://localhost:5000/api/jobs"
echo ""
echo "🚀 Quick Start Commands:"
echo "   # Check system stats"
echo "   curl http://localhost:5000/api/stats"
echo ""
echo "   # Start metadata fetch for sample channels"
echo "   curl -X POST http://localhost:5000/api/fetch-metadata \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"limit\": 10}'"
echo ""
echo "   # Discover related channels"
echo "   curl -X POST http://localhost:5000/api/discover-channels \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"limit\": 5, \"methods\": [\"youtube_featured\", \"similar_content\"]}'"
echo ""
echo "📝 Useful Commands:"
echo "   # View logs:           $COMPOSE_CMD logs -f app"
echo "   # Stop services:       $COMPOSE_CMD down"
echo "   # Restart services:    $COMPOSE_CMD restart"
echo "   # Access database:     $COMPOSE_CMD exec db psql -U youtube -d youtube_channels"
echo "   # Access Redis:        $COMPOSE_CMD exec redis redis-cli"
echo ""
echo "🔧 Available Discovery Methods (no external APIs needed):"
echo "   - youtube_featured:     Uses YouTube's featured channels"
echo "   - similar_content:      Analyzes video content and descriptions"
echo "   - youtube_collaborations: Finds channels mentioned in videos"
echo "   - related_channels:     Web scraping of SocialBlade"
echo ""
echo "⚠️  Note: NOXINFLUENCER and CHANNELCRAWLER APIs are not publicly available"
echo "   The system uses alternative discovery methods instead"
echo ""

# Check if we have YouTube API keys configured
if $COMPOSE_CMD exec -T app python -c "
import os
from dotenv import load_dotenv
load_dotenv()
keys = [os.getenv(f'YOUTUBE_API_KEY_{i}') for i in range(1, 6)]
valid_keys = [k for k in keys if k and k != 'your-youtube-api-key-{}'.format(keys.index(k)+1)]
print(f'YouTube API Keys configured: {len(valid_keys)}')
if len(valid_keys) == 0:
    print('⚠️  WARNING: No valid YouTube API keys found!')
    print('   Please edit .env file with your actual API keys')
    exit(1)
" 2>/dev/null; then
    echo "✅ YouTube API keys are configured"
else
    echo "⚠️  WARNING: Please configure your YouTube API keys in .env file"
fi

echo ""
echo "🎯 System is ready for data processing!"