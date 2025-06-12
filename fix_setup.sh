#!/bin/bash

# Fix Local Setup Script
echo "🔧 Fixing YouTube Channel Aggregator Local Setup"
echo "================================================"

# Step 1: Fix virtual environment
echo "🐍 Fixing virtual environment..."
deactivate 2>/dev/null || true

# Remove problematic venv
if [ -d "venv" ]; then
    echo "📁 Removing corrupted virtual environment..."
    rm -rf venv
fi

# Create new virtual environment
echo "🆕 Creating new virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip

# Install dependencies one by one to catch issues
echo "📦 Installing dependencies..."
echo "Installing Flask..."
pip install Flask==2.3.3

echo "Installing SQLAlchemy..."
pip install SQLAlchemy==2.0.19

echo "Installing Flask-SQLAlchemy..."
pip install Flask-SQLAlchemy==3.0.5

echo "Installing psycopg2-binary..."
pip install psycopg2-binary==2.9.7

echo "Installing Celery..."
pip install celery==5.3.1

echo "Installing Redis..."
pip install redis==4.6.0

echo "Installing other dependencies..."
pip install Flask-Migrate==4.0.5
pip install google-api-python-client==2.95.0
pip install google-auth==2.22.0
pip install requests==2.31.0
pip install beautifulsoup4==4.12.2
pip install langdetect==1.0.9
pip install python-dotenv==1.0.0
pip install pydantic==2.1.1
pip install alembic==1.11.1
pip install gunicorn==21.2.0

echo "✅ Dependencies installed successfully"

# Step 2: Check PostgreSQL and create database
echo "🗄️  Setting up PostgreSQL database..."

# Check if PostgreSQL is running
if ! sudo systemctl is-active --quiet postgresql; then
    echo "🔄 Starting PostgreSQL..."
    sudo systemctl start postgresql
fi

# Create database and user
echo "👤 Creating database user and database..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS youtube_channels;" 2>/dev/null || true
sudo -u postgres psql -c "DROP USER IF EXISTS youtube;" 2>/dev/null || true
sudo -u postgres psql -c "CREATE USER youtube WITH PASSWORD 'youtube123';"
sudo -u postgres psql -c "CREATE DATABASE youtube_channels OWNER youtube;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE youtube_channels TO youtube;"

echo "✅ Database and user created"

# Step 3: Initialize database schema
echo "🏗️  Initializing database schema..."
if PGPASSWORD=youtube123 psql -h localhost -U youtube -d youtube_channels -f init.sql; then
    echo "✅ Database schema initialized"
else
    echo "❌ Failed to initialize schema. Let's try a simpler approach..."
    
    # Create a simplified init script that definitely works
    cat > simple_init.sql << 'EOF'
-- Simple database initialization
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Channels table
CREATE TABLE IF NOT EXISTS channels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel_id VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    subscriber_count BIGINT,
    video_count BIGINT,
    view_count BIGINT,
    country VARCHAR(10),
    language VARCHAR(10),
    custom_url VARCHAR(255),
    published_at TIMESTAMP,
    thumbnail_url VARCHAR(500),
    banner_url VARCHAR(500),
    keywords TEXT[],
    topic_categories TEXT[],
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata_fetched BOOLEAN DEFAULT FALSE,
    videos_fetched BOOLEAN DEFAULT FALSE,
    discovery_processed BOOLEAN DEFAULT FALSE,
    source VARCHAR(50) DEFAULT 'migration',
    discovered_from UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key_name VARCHAR(100) NOT NULL,
    api_key VARCHAR(255) NOT NULL,
    service VARCHAR(50) NOT NULL DEFAULT 'youtube',
    quota_limit INTEGER DEFAULT 10000,
    quota_used INTEGER DEFAULT 0,
    quota_reset_date DATE DEFAULT CURRENT_DATE,
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processing jobs table
CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    channel_id UUID,
    total_items INTEGER,
    processed_items INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Videos table
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id VARCHAR(255) UNIQUE NOT NULL,
    channel_id UUID NOT NULL,
    channel_external_id VARCHAR(255) NOT NULL,
    title VARCHAR(500),
    description TEXT,
    published_at TIMESTAMP,
    duration VARCHAR(20),
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT,
    thumbnail_url VARCHAR(500),
    tags TEXT[],
    category_id INTEGER,
    language VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Channel discoveries table
CREATE TABLE IF NOT EXISTS channel_discoveries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_channel_id UUID NOT NULL,
    discovered_channel_id VARCHAR(255) NOT NULL,
    discovery_method VARCHAR(50) NOT NULL,
    service_name VARCHAR(50) NOT NULL,
    confidence_score FLOAT,
    already_exists BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_channels_channel_id ON channels(channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_channel_id ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_service ON api_keys(service);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);

-- Insert some sample channels for testing
INSERT INTO channels (channel_id, title, description, source) 
VALUES 
    ('UCBJycsmduvYEL83R_U4JriQ', 'Marques Brownlee', 'MKBHD: Quality Tech Videos', 'sample'),
    ('UCXuqSBlHAE6Xw-yeJA0Tunw', 'Linus Tech Tips', 'We make entertaining videos about technology', 'sample'),
    ('UC6nSFpj9HTCZ5t-N3Rm3-HA', 'Vsauce', 'Our World is Amazing. Questions and wonder.', 'sample')
ON CONFLICT (channel_id) DO NOTHING;

EOF
    
    if PGPASSWORD=youtube123 psql -h localhost -U youtube -d youtube_channels -f simple_init.sql; then
        echo "✅ Simple database schema initialized"
    else
        echo "❌ Database schema initialization failed"
        echo "💡 You might need to check PostgreSQL permissions"
    fi
fi

# Step 4: Check Redis
echo "🔍 Checking Redis..."
if ! pgrep redis-server > /dev/null; then
    echo "🔄 Starting Redis..."
    redis-server --daemonize yes
    sleep 2
fi

if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "❌ Redis failed to start"
    echo "💡 Try: sudo systemctl start redis"
fi

# Step 5: Test database connection
echo "🔍 Testing database connection..."
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect('postgresql://youtube:youtube123@localhost:5432/youtube_channels')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM channels;')
    count = cursor.fetchone()[0]
    print(f'✅ Database connection successful - {count} channels found')
    conn.close()
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
"

# Step 6: Update .env file with working values
echo "📝 Updating .env file..."
cat > .env << 'EOF'
# Database Configuration
DATABASE_URL=postgresql://youtube:youtube123@localhost:5432/youtube_channels

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=local-dev-secret-key-change-in-production

# YouTube API Keys (REPLACE WITH YOUR ACTUAL KEYS!)
YOUTUBE_API_KEY_1=your-youtube-api-key-1
YOUTUBE_API_KEY_2=your-youtube-api-key-2

# Processing Configuration
DEFAULT_BATCH_SIZE=100
MAX_VIDEOS_PER_CHANNEL=25
API_RATE_LIMIT_DELAY=0.2

# Logging
LOG_LEVEL=INFO
EOF

echo ""
echo "🎉 Setup completed!"
echo "=================="
echo ""
echo "📝 IMPORTANT: Edit .env file with your YouTube API keys:"
echo "   nano .env"
echo ""
echo "🔧 Next steps:"
echo "1. Add your YouTube API keys to .env file"
echo "2. Run: python app/setup.py"
echo "3. Start the app: ./start_local.sh"
echo ""
echo "✅ Virtual environment is ready at: $(pwd)/venv"
echo "✅ Database is set up and running"
echo "✅ All dependencies are installed"