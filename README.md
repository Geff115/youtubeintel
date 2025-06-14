# YouTube Channel Data Aggregation System
A production-ready, scalable system for processing millions of YouTube channels.
Handle 5-15M channel IDs with comprehensive metadata fetching, video analysis, and intelligent channel discovery.

## 🚀 Features
### Core Capabilities
- **Mass Data Processing: Handle 5-15M YouTube channel IDs efficiently**
- **YouTube API Integration: Fetch comprehensive metadata and video data**
- **Intelligent Discovery: Find related channels using multiple methods**
- **Cloud-Ready Architecture: UPSTASH Redis for global deployment**
- **Real-time Monitoring: Track processing progress and system health**

### Advanced Features
- **Smart API Key Rotation: Automatic quota management across multiple keys**
- **Batch Processing: Configurable batch sizes for optimal performance**
- **Error Recovery: Robust handling with automatic retry mechanisms**
- **Language Detection: Automatic content language identification**
- **Scalable Workers: Celery-based async processing with horizontal scaling**

## 🏗️ Architecture

                        ┌────────────────────┐
                        │     Flask API      │
                        │   (Port 5000)      │
                        └────────┬───────────┘
                                 │
                                 ▼
                        ┌────────┴──────────┐
                        │     Celery        │
                        │     Workers       │
                        └────────┬──────────┘
                                 │
                                 ▼
                        ┌────────┴──────────┐
                        │   PostgreSQL DB   │
                        └───────────────────┘

    ┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
    │     UPSTASH        │     │   YouTube API       │     │   Discovery        │
    │     Redis          │     │   Integration       │     │   Services         │
    └────────────────────┘     └────────────────────┘     └────────────────────┘

## 📊 Performance

| Operation           | Scale         | Processing Time* | API Calls |
|---------------------|---------------|------------------|-----------|
| Channel Migration   | 15M channels  | 4–6 hours        | 0         |
| Metadata Fetching   | 15M channels  | 2–3 weeks        | 15M       |
| Video Processing    | 5M channels   | 2–4 weeks        | 10M       |
| Channel Discovery   | 1M channels   | 1–2 weeks        | 2M        |

*With 5+ API keys and optimized batch sizes

## Technology Stack
- **Backend: Python 3.11+, Flask**
- **Database: PostgreSQL 15+ with optimized indexing**
- **Message Broker: UPSTASH Redis (cloud) or local Redis**
- **Task Queue: Celery with Redis backend**
- **APIs: YouTube Data API v3, multiple discovery services**
- **Deployment: Docker, Docker Compose**

## 🚦 Quick Start

### Prerequisites
- **Python 3.11+**
- **PostgreSQL 15+**
- **Redis 6+ (or UPSTASH Redis account)**
- **YouTube Data API keys**

### 1. Clone and Setup
```bash
git clone https://<your_github_personal_access_token>@github.com/Geff115/youtube_channel_aggregator.git
cd youtube-channel-aggregator
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 2. Environment Configuration
```bash
nano .env  # Configure your credentials
```

#### Required Environment Variables:
```env
# Database
DATABASE_URL="postgresql://username:password@host:port/database"

# Redis (choose one)
REDIS_URL=redis://localhost:6379/0                    # Local Redis
UPSTASH_REDIS_URL=https://your-endpoint.upstash.io    # Cloud Redis
UPSTASH_REDIS_REST_TOKEN=your-upstash-token

# YouTube API Keys (add multiple for scale, you can add 5 for better randomization)
YOUTUBE_API_KEY_1=your-youtube-api-key-1
YOUTUBE_API_KEY_2=your-youtube-api-key-2
YOUTUBE_API_KEY_3=your-youtube-api-key-3
YOUTUBE_API_KEY_4=your-youtube-api-key-4
YOUTUBE_API_KEY_5=your-youtube-api-key-5

# Processing Configuration
DEFAULT_BATCH_SIZE=100
MAX_VIDEOS_PER_CHANNEL=25
API_RATE_LIMIT_DELAY=0.2

# Application
SECRET_KEY=your-secret-key
ENVIRONMENT=production  # or development
```

### 3. Database Setup
```bash
# Initialize database schema
psql -h localhost -U username -d database_name -f init.sql

# Or use Docker
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=youtube \
  -e POSTGRES_PASSWORD=youtube123 \
  -e POSTGRES_DB=youtube_channels \
  postgres:15
```

### 4. Start Services
#### Production Mode (Recommended):
```bash
chmod +x start_production.sh
./start_production.sh
```

#### Development Mode:
```bash
# Terminal 1: Flask app
cd app && python3 app.py

# Terminal 2: Celery worker
cd app && celery -A tasks worker --loglevel=info

# Terminal 3: Celery beat (optional)
cd app && celery -A tasks beat --loglevel=info
```

### 5. Verify Installation
```bash
# Health check
curl http://localhost:5000/health

# System status
curl http://localhost:5000/api/system-status

# Test Redis connection
curl http://localhost:5000/api/redis-test
```

## 📖 API Documentation
### 🧪 System Endpoints
| Endpoint            | Method | Description                      |
|---------------------|--------|----------------------------------|
| `/health`           | GET    | Application health check         |
| `/api/stats`        | GET    | Basic system statistics          |
| `/api/system-status`| GET    | Comprehensive system status      |
| `/api/redis-test`   | GET    | Redis connection test            |
| `/api/worker-status`| GET    | Celery worker information        |

### 🔧 Data Management
| Endpoint              | Method | Description                     |
|-----------------------|--------|---------------------------------|
| `/api/channels`       | GET    | List channels with pagination   |
| `/api/jobs`           | GET    | List processing jobs            |
| `/api/jobs/{job_id}`  | GET    | Get specific job status         |
| `/api/api-keys`       | GET    | List API keys (masked)          |

### 📦 Batch Processing (Production Scale)
| Endpoint               | Method | Description                                |
|------------------------|--------|--------------------------------------------|
| `/api/batch-metadata`  | POST   | Process metadata for millions of channels  |
| `/api/batch-videos`    | POST   | Fetch videos for channels with metadata    |
| `/api/batch-discovery` | POST   | Discover related channels at scale         |
| `/api/migrate`         | POST   | Import millions of channel IDs             |

### 📂 Bulk Operations
| Endpoint                  | Method | Description                        |
|---------------------------|--------|------------------------------------|
| `/api/bulk-add-channels` | POST   | Add channels in bulk from JSON     |
| `/api/test-youtube`      | POST   | Test YouTube API connectivity      |

### 🎯 Job Monitoring
| Use Case             | Example Command                                               |
|----------------------|---------------------------------------------------------------|
| List all jobs        | `curl http://localhost:5000/api/jobs`                         |
| Get job by ID        | `curl http://localhost:5000/api/jobs/{job-id}`                |
| Filter by status     | `curl "http://localhost:5000/api/jobs?status=running"`        |

## 🎯 Usage Examples
### Basic Operations
```bash
# Check system health
curl http://localhost:5000/health

# View system statistics
curl http://localhost:5000/api/stats
```

### Bulk Channel Addition
```bash
curl -X POST http://localhost:5000/api/bulk-add-channels \
  -H 'Content-Type: application/json' \
  -d '{
    "channels": [
      {"channel_id": "UCBJycsmduvYEL83R_U4JriQ", "title": "MKBHD"},
      {"channel_id": "UCXuqSBlHAE6Xw-yeJA0Tunw", "title": "Linus Tech Tips"}
    ],
    "source": "manual_addition"
  }'
  ```

### Large Scale Metadata Processing
```bash
curl -X POST http://localhost:5000/api/batch-metadata \
  -H 'Content-Type: application/json' \
  -d '{
    "batch_size": 5000,
    "total_limit": 100000
  }'
```

### Video Data Fetching
```bash
curl -X POST http://localhost:5000/api/batch-videos \
  -H 'Content-Type: application/json' \
  -d '{
    "batch_size": 1000,
    "total_limit": 50000
  }'
```

### Channel Discovery
```bash
curl -X POST http://localhost:5000/api/batch-discovery \
  -H 'Content-Type: application/json' \
  -d '{
    "batch_size": 500,
    "total_limit": 10000
  }'
```

### Data Migration
```bash
# From CSV file
curl -X POST http://localhost:5000/api/migrate \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "csv",
    "source_path": "/path/to/channels.csv",
    "batch_size": 10000
  }'

# From MySQL database
curl -X POST http://localhost:5000/api/migrate \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "mysql",
    "source_path": "mysql://user:pass@host:3306/database",
    "batch_size": 5000
  }'
```

### Job Monitoring
```bash
# List all jobs
curl http://localhost:5000/api/jobs

# Get specific job status
curl http://localhost:5000/api/jobs/{job-id}

# Filter by status
curl "http://localhost:5000/api/jobs?status=running"
```

## 🗄️ Database Schema
### Core Tables
#### Channels: Store channel metadata and processing status
```sql
- id (UUID, Primary Key)
- channel_id (String, Unique)
- title, description, subscriber_count, video_count, view_count
- metadata_fetched, videos_fetched, discovery_processed (Boolean)
- created_at, updated_at (Timestamp)
```

### Videos: Store video information linked to channels
```sql
- id (UUID, Primary Key)
- video_id (String, Unique)
- channel_id (UUID, Foreign Key)
- title, description, published_at, duration
- view_count, like_count, comment_count
- tags (Array), category_id, language
```

### API Keys: Manage YouTube API keys with quota tracking
```sql
- id (UUID, Primary Key)
- key_name, api_key, service
- quota_limit, quota_used, quota_reset_date
- is_active, last_used, error_count
```

### Processing Jobs: Track async job status and progress
```sql
- id (UUID, Primary Key)
- job_type, status, total_items, processed_items
- error_message, started_at, completed_at
```

### Channel Discoveries: Record discovered channel relationships
```sql
- id (UUID, Primary Key)
- source_channel_id, discovered_channel_id
- discovery_method, service_name, confidence_score
```

## 🚀 Deployment
### Docker Deployment

```bash
# Start all services
docker-compose up -d

# Scale workers
docker-compose up -d --scale celery_worker=4

# View logs
docker-compose logs -f app
```

### Production Deployment
#### Cloud Platforms:
- **AWS ECS/EKS with UPSTASH Redis**
- **Google Cloud Run with Cloud Memorystore**
- **Azure Container Instances with Azure Cache for Redis**

### Configuration for scale:
```bash
# Environment variables for production
ENVIRONMENT=production
CELERY_CONCURRENCY=8
DEFAULT_BATCH_SIZE=5000
MAX_VIDEOS_PER_CHANNEL=50

# Multiple API keys for higher throughput
YOUTUBE_API_KEY_1=key1
YOUTUBE_API_KEY_2=key2
# ... up to YOUTUBE_API_KEY_10=key10
```

## 📊 Monitoring
### System Health
```bash
# Application metrics
curl http://localhost:5000/api/system-status

# Worker status
curl http://localhost:5000/api/worker-status

# Redis health
curl http://localhost:5000/api/redis-test
```

### Job Monitoring
```bash
# Active jobs
curl "http://localhost:5000/api/jobs?status=running"

# Failed jobs
curl "http://localhost:5000/api/jobs?status=failed"

# Job details
curl http://localhost:5000/api/jobs/{job-id}
```

## Performance Metrics
- **API Quota Usage: Track across multiple YouTube API keys**
- **Processing Speed: Channels/videos processed per hour**
- **Error Rates: Failed requests and retry attempts**
- **Worker Performance: Task completion times and load**

## Performance Optimization
### For Large Datasets (10M+ channels):
1. Increase batch sizes: DEFAULT_BATCH_SIZE=10000
2. Add more workers: CELERY_CONCURRENCY=12
3. Use more API keys: Up to 10 YouTube API keys
4. Optimize database: Add indexes, use connection pooling
5. Scale horizontally: Multiple worker instances

## Memory Optimization:
```bash
# Limit worker memory usage
CELERY_WORKER_MAX_MEMORY_PER_CHILD=500000  # 500MB
CELERY_WORKER_MAX_TASKS_PER_CHILD=1000
```

## 📄 License
This project is licensed under the MIT License

## 🎯 Project Status
Current Version: 1.0.0
Status: Production Ready ✅
Tested Scale: 15M+ channels ✅
Cloud Ready: UPSTASH Redis ✅
Monitoring: Real-time job tracking ✅
Built with ❤️ for scalable YouTube data processing.