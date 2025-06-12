#!/bin/bash

# Local Development Setup for YouTube Channel Aggregator
echo "🚀 Setting up YouTube Channel Aggregator for Local Development"
echo "=============================================================="

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "💡 Recommendation: Create and activate a virtual environment first"
    echo "   python -m venv venv"
    echo "   source venv/bin/activate  # Linux/Mac"
    echo "   # or venv\\Scripts\\activate  # Windows"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ Virtual environment detected: $VIRTUAL_ENV"
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file for local development..."
    cat > .env << 'EOF'
# Database Configuration (Local PostgreSQL)
DATABASE_URL="postgresql://youtube:youtube123@localhost:5432/youtube_channels"

# Redis Configuration (Local Redis)
REDIS_URL=redis://localhost:6379/0

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=local-dev-secret-key-change-in-production

# YouTube API Keys (add your actual keys here)
YOUTUBE_API_KEY_1=your-youtube-api-key-1
YOUTUBE_API_KEY_2=your-youtube-api-key-2

# Processing Configuration
DEFAULT_BATCH_SIZE=100
MAX_VIDEOS_PER_CHANNEL=25
API_RATE_LIMIT_DELAY=0.2

# Logging
LOG_LEVEL=INFO
EOF
    echo "✅ Created .env file"
    echo "⚠️  IMPORTANT: Edit .env file with your actual YouTube API keys!"
    echo ""
else
    echo "✅ .env file exists"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
if pip install -r requirements.txt; then
    echo "✅ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Check for PostgreSQL
echo "🔍 Checking for PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL client found"
    
    # Check if PostgreSQL server is running
    if pg_isready -h localhost -p 5432 &> /dev/null; then
        echo "✅ PostgreSQL server is running"
    else
        echo "❌ PostgreSQL server is not running"
        echo "💡 Please start PostgreSQL server:"
        echo "   # Ubuntu/Debian: sudo systemctl start postgresql"
        echo "   # macOS with Homebrew: brew services start postgresql"
        echo "   # Or install PostgreSQL if not installed"
        exit 1
    fi
else
    echo "❌ PostgreSQL not found"
    echo "💡 Please install PostgreSQL:"
    echo "   # Ubuntu/Debian: sudo apt install postgresql postgresql-contrib"
    echo "   # macOS: brew install postgresql"
    echo "   # Or use Docker: docker run -p 5432:5432 -e POSTGRES_USER=youtube -e POSTGRES_PASSWORD=youtube123 -e POSTGRES_DB=youtube_channels postgres:15"
    exit 1
fi

# Check for Redis
echo "🔍 Checking for Redis..."
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis client found"
    
    # Check if Redis server is running
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis server is running"
    else
        echo "❌ Redis server is not running"
        echo "💡 Please start Redis server:"
        echo "   # Ubuntu/Debian: sudo systemctl start redis"
        echo "   # macOS with Homebrew: brew services start redis"
        echo "   # Or start manually: redis-server"
        echo "   # Or use Docker: docker run -p 6379:6379 redis:7-alpine"
        exit 1
    fi
else
    echo "❌ Redis not found"
    echo "💡 Please install Redis:"
    echo "   # Ubuntu/Debian: sudo apt install redis-server"
    echo "   # macOS: brew install redis"
    echo "   # Or use Docker: docker run -p 6379:6379 redis:7-alpine"
    exit 1
fi

# Create database and user if they don't exist
echo "🗄️  Setting up database..."
read -p "Enter PostgreSQL superuser name (usually 'postgres'): " pg_superuser
pg_superuser=${pg_superuser:-postgres}

# Check if database exists
if psql -h localhost -U $pg_superuser -lqt | cut -d \| -f 1 | grep -qw youtube_channels; then
    echo "✅ Database 'youtube_channels' already exists"
else
    echo "📝 Creating database and user..."
    
    # Create user and database
    psql -h localhost -U $pg_superuser -c "CREATE USER youtube WITH PASSWORD 'youtube123';" 2>/dev/null || echo "User 'youtube' might already exist"
    psql -h localhost -U $pg_superuser -c "CREATE DATABASE youtube_channels OWNER youtube;" 2>/dev/null || echo "Database 'youtube_channels' might already exist"
    psql -h localhost -U $pg_superuser -c "GRANT ALL PRIVILEGES ON DATABASE youtube_channels TO youtube;" 2>/dev/null
    
    echo "✅ Database setup completed"
fi

# Initialize database schema
echo "🏗️  Initializing database schema..."
if psql -h localhost -U youtube -d youtube_channels -f init.sql; then
    echo "✅ Database schema initialized"
else
    echo "❌ Failed to initialize database schema"
    echo "💡 You might need to run this manually:"
    echo "   psql -h localhost -U youtube -d youtube_channels -f init.sql"
fi

echo ""
echo "🎉 Local setup completed!"
echo "========================="
echo ""
echo "📝 Next steps:"
echo "1. Edit .env file with your YouTube API keys"
echo "2. Run the setup script: python setup.py"
echo "3. Start the application: python app/app.py"
echo "4. In another terminal, start Celery worker: celery -A app.tasks worker --loglevel=info"
echo ""
echo "🔧 Development commands:"
echo "   # Start Flask app"
echo "   cd app && python app.py"
echo ""
echo "   # Start Celery worker (in another terminal)"
echo "   cd app && celery -A tasks worker --loglevel=info"
echo ""
echo "   # Start Celery beat scheduler (optional, in another terminal)"
echo "   cd app && celery -A tasks beat --loglevel=info"
echo ""
echo "🌐 Once running, access:"
echo "   Health Check: http://localhost:5000/health"
echo "   System Stats: http://localhost:5000/api/stats"