#!/usr/bin/env python3
"""
Setup script for YouTube Channel Data Aggregation System
"""

import os
import sys
import subprocess
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import db, APIKey
from dotenv import load_dotenv
import uuid

load_dotenv()

def run_command(command, check=True):
    """Run shell command"""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, check=check)
    return result.returncode == 0

def setup_environment():
    """Setup environment variables"""
    if not os.path.exists('.env'):
        print("Creating .env file from template...")
        if os.path.exists('.env'):
            with open('.env', 'r') as src, open('.env', 'w') as dst:
                dst.write(src.read())
            print("✓ Created .env file. Please edit it with your API keys.")
        else:
            print("✗ .env not found")
            return False
    else:
        print("✓ .env file already exists")
    return True

def setup_database():
    """Initialize database"""
    print("Setting up database...")
    
    # Wait for database to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost:5432/youtube_channels')
            engine = create_engine(DATABASE_URL)
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                print("✓ Database connection successful")
                break
        except Exception as e:
            if i == max_retries - 1:
                print(f"✗ Database connection failed after {max_retries} attempts: {e}")
                return False
            print(f"Waiting for database... (attempt {i+1}/{max_retries})")
            import time
            time.sleep(2)
    
    return True

def add_sample_api_keys():
    """Add sample API keys from environment"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost:5432/youtube_channels')
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        # Add YouTube API keys
        youtube_keys = []
        for i in range(1, 11):  # Check for up to 10 keys
            key = os.getenv(f'YOUTUBE_API_KEY_{i}')
            if key:
                youtube_keys.append(key)
        
        if youtube_keys:
            print(f"Adding {len(youtube_keys)} YouTube API keys...")
            for i, key in enumerate(youtube_keys, 1):
                existing = session.query(APIKey).filter_by(api_key=key).first()
                if not existing:
                    api_key = APIKey(
                        key_name=f'youtube_key_{i}',
                        api_key=key,
                        service='youtube',
                        quota_limit=10000
                    )
                    session.add(api_key)
            
            session.commit()
            print("✓ YouTube API keys added")
        else:
            print("⚠ No YouTube API keys found in environment")
        
        # External services note
        print("ℹ️  Note: NOXINFLUENCER and CHANNELCRAWLER don't offer public APIs")
        print("ℹ️  System will use web scraping and YouTube-native discovery instead")
        
        session.commit()
        session.close()
        return True
        
    except Exception as e:
        print(f"✗ Failed to add API keys: {e}")
        return False

def create_sample_data():
    """Create sample data for testing"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/youtube_channels')
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        # Sample channels for testing
        sample_channels = [
            {
                'channel_id': 'UCBJycsmduvYEL83R_U4JriQ',  # Marques Brownlee
                'title': 'Marques Brownlee',
                'description': 'MKBHD: Quality Tech Videos | Creator of TechMemes',
                'source': 'sample'
            },
            {
                'channel_id': 'UCXuqSBlHAE6Xw-yeJA0Tunw',  # Linus Tech Tips
                'title': 'Linus Tech Tips',
                'description': 'We make entertaining videos about technology, including tech reviews, showcases and other content.',
                'source': 'sample'
            },
            {
                'channel_id': 'UC6nSFpj9HTCZ5t-N3Rm3-HA',  # Vsauce
                'title': 'Vsauce',
                'description': 'Our World is Amazing. Curiosity and wonder are two of the most important things humans can experience.',
                'source': 'sample'
            }
        ]
        
        from models import Channel
        
        for channel_data in sample_channels:
            existing = session.query(Channel).filter_by(channel_id=channel_data['channel_id']).first()
            if not existing:
                channel = Channel(
                    channel_id=channel_data['channel_id'],
                    title=channel_data['title'],
                    description=channel_data['description'],
                    source=channel_data['source']
                )
                session.add(channel)
        
        session.commit()
        session.close()
        print("✓ Sample channels added")
        return True
        
    except Exception as e:
        print(f"✗ Failed to create sample data: {e}")
        return False

def check_services():
    """Check if required services are running"""
    print("Checking services...")
    
    # Check PostgreSQL
    try:
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost:5432/youtube_channels')
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ PostgreSQL is running")
    except Exception as e:
        print(f"✗ PostgreSQL connection failed: {e}")
        return False
    
    # Check Redis
    try:
        import redis
        REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        r = redis.from_url(REDIS_URL)
        r.ping()
        print("✓ Redis is running")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        return False
    
    return True

def main():
    """Main setup function"""
    print("🚀 YouTube Channel Data Aggregation System Setup")
    print("=" * 50)
    
    # Check if running in Docker
    in_docker = os.path.exists('/.dockerenv')
    print(f"Environment: {'Docker' if in_docker else 'Local'}")
    
    # Step 1: Setup environment
    if not setup_environment():
        print("❌ Environment setup failed")
        sys.exit(1)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Step 2: Check services
    if not check_services():
        if not in_docker:
            print("💡 Tip: Make sure to run 'docker-compose up -d' first")
        print("❌ Service check failed")
        sys.exit(1)
    
    # Step 3: Setup database
    if not setup_database():
        print("❌ Database setup failed")
        sys.exit(1)
    
    # Step 4: Add API keys
    if not add_sample_api_keys():
        print("❌ API key setup failed")
        sys.exit(1)
    
    # Step 5: Create sample data
    if not create_sample_data():
        print("❌ Sample data creation failed")
        sys.exit(1)
    
    print("\n🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Edit .env file with your actual API keys")
    print("2. Start the application: docker-compose up")
    print("3. Access the API at: http://localhost:5000")
    print("4. Check health: http://localhost:5000/health")
    print("5. View stats: http://localhost:5000/api/stats")
    
    print("\nUseful commands:")
    print("- Start migration: POST /api/migrate")
    print("- Fetch metadata: POST /api/fetch-metadata")
    print("- Fetch videos: POST /api/fetch-videos")
    print("- Discover channels: POST /api/discover-channels")

if __name__ == '__main__':
    main()