from celery import Celery
from celery.signals import worker_ready
import os
from datetime import datetime, timedelta
import json
import csv
try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("⚠️  MySQL connector not available - MySQL migration will be disabled")
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import uuid
import logging
from langdetect import detect
import requests
import time
import random

from app.models import Channel, Video, APIKey, ProcessingJob, ChannelDiscovery
from app.youtube_service import YouTubeService
from app.external_services import ExternalChannelDiscovery

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery with Redis configuration
from app.redis_config import get_celery_broker_url

celery_app = Celery('youtube_processor')

# Get broker URL (handles both local and UPSTASH Redis)
broker_url = get_celery_broker_url()

# Optional SSL config for rediss://
import ssl
broker_use_ssl = None
redis_backend_use_ssl = None
if broker_url.startswith('rediss://'):
    ssl_config = {
        # Use CERT_REQUIRED for secure connections in production.
        # Could be changed to CERT_NONE if having cert verification issues.
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    }
    broker_use_ssl = ssl_config
    redis_backend_use_ssl = ssl_config
    print("✅ Using SSL with CERT_REQUIRED for Redis")

celery_app.conf.update(
    broker_url=broker_url,
    result_backend=broker_url,
    broker_use_ssl=broker_use_ssl,
    redis_backend_use_ssl=redis_backend_use_ssl,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True, # Retry connection on startup
    worker_prefetch_multiplier=1,  # Better for production
    task_acks_late=True,  # Acknowledge after task completion
    worker_max_tasks_per_child=1000,  # Restart workers periodically
    task_routes={
        'tasks.migrate_channel_data': {'queue': 'migration'},
        'tasks.fetch_channel_metadata': {'queue': 'youtube_api'},
        'tasks.fetch_channel_videos': {'queue': 'youtube_api'},
        'tasks.discover_related_channels': {'queue': 'discovery'},
        'tasks.batch_process_channels': {'queue': 'batch_processing'},
    },
    beat_schedule={
        'reset-api-quotas': {
            'task': 'tasks.reset_api_quotas',
            'schedule': 3600.0,  # Every hour
        },
        'cleanup_old_jobs': {
            'task': 'tasks.cleanup_old_jobs',
            'schedule': 86400.0,  # Daily
        },
        'monitor_system_health': {
            'task': 'tasks.monitor_system_health',
            'schedule': 300.0,  # Every 5 minutes
        },
    }
)

# Database setup for Celery tasks
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/youtube_channels')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """Get database session for Celery tasks"""
    return SessionLocal()

@celery_app.task(bind=True)
def migrate_channel_data(self, job_id, source_type, source_path, batch_size=1000):
    """Migrate channel data from existing sources"""
    session = get_db_session()
    
    try:
        # Get and start job
        job = session.query(ProcessingJob).filter_by(id=uuid.UUID(job_id)).first()
        if not job:
            raise Exception(f"Job {job_id} not found")
        
        job.start()
        session.commit()
        
        logger.info(f"Starting migration from {source_type}: {source_path}")
        
        if source_type == 'mysql':
            total_migrated = migrate_from_mysql(session, source_path, batch_size)
        elif source_type == 'csv':
            total_migrated = migrate_from_csv(session, source_path, batch_size)
        elif source_type == 'json':
            total_migrated = migrate_from_json(session, source_path, batch_size)
        else:
            raise Exception(f"Unsupported source type: {source_type}")
        
        job.total_items = total_migrated
        job.processed_items = total_migrated
        job.complete()
        session.commit()
        
        logger.info(f"Migration completed: {total_migrated} channels migrated")
        return {'status': 'completed', 'migrated_count': total_migrated}
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        job.fail(str(e))
        session.commit()
        return {'status': 'failed', 'error': str(e)}
    
    finally:
        session.close()

def migrate_from_mysql(session, connection_string, batch_size):
    """Migrate from MySQL database"""
    if not MYSQL_AVAILABLE:
        raise Exception("MySQL connector not available. Install with: pip install mysql-connector-python")
    
    # Parse connection string
    # Format: mysql://user:password@host:port/database
    import re
    match = re.match(r'mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', connection_string)
    if not match:
        raise Exception("Invalid MySQL connection string format")
    
    user, password, host, port, database = match.groups()
    
    # Connect to MySQL
    mysql_conn = mysql.connector.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database
    )
    
    cursor = mysql_conn.cursor(dictionary=True)
    
    # Assuming channels table exists with channel_id column
    cursor.execute("SELECT COUNT(*) as count FROM channels")
    total_count = cursor.fetchone()['count']
    
    migrated = 0
    offset = 0
    
    while offset < total_count:
        cursor.execute(f"SELECT * FROM channels LIMIT {batch_size} OFFSET {offset}")
        channels = cursor.fetchall()
        
        for channel_data in channels:
            # Check if channel already exists
            existing = session.query(Channel).filter_by(
                channel_id=channel_data['channel_id']
            ).first()
            
            if not existing:
                channel = Channel(
                    channel_id=channel_data['channel_id'],
                    title=channel_data.get('title'),
                    description=channel_data.get('description'),
                    source='migration'
                )
                session.add(channel)
                migrated += 1
        
        session.commit()
        offset += batch_size
        logger.info(f"Migrated {migrated}/{total_count} channels")
    
    cursor.close()
    mysql_conn.close()
    
    return migrated

def migrate_from_csv(session, file_path, batch_size):
    """Migrate from CSV file"""
    migrated = 0
    
    with open(file_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        batch = []
        for row in reader:
            # Check if channel already exists
            existing = session.query(Channel).filter_by(
                channel_id=row['channel_id']
            ).first()
            
            if not existing:
                channel = Channel(
                    channel_id=row['channel_id'],
                    title=row.get('title', ''),
                    description=row.get('description', ''),
                    source='migration'
                )
                batch.append(channel)
                
                if len(batch) >= batch_size:
                    session.add_all(batch)
                    session.commit()
                    migrated += len(batch)
                    batch = []
                    logger.info(f"Migrated {migrated} channels")
        
        # Handle remaining batch
        if batch:
            session.add_all(batch)
            session.commit()
            migrated += len(batch)
    
    return migrated

def migrate_from_json(session, file_path, batch_size):
    """Migrate from JSON file"""
    migrated = 0
    
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        
        # Assume data is array of channel objects
        channels = data if isinstance(data, list) else data.get('channels', [])
        
        batch = []
        for channel_data in channels:
            # Check if channel already exists
            existing = session.query(Channel).filter_by(
                channel_id=channel_data['channel_id']
            ).first()
            
            if not existing:
                channel = Channel(
                    channel_id=channel_data['channel_id'],
                    title=channel_data.get('title', ''),
                    description=channel_data.get('description', ''),
                    source='migration'
                )
                batch.append(channel)
                
                if len(batch) >= batch_size:
                    session.add_all(batch)
                    session.commit()
                    migrated += len(batch)
                    batch = []
                    logger.info(f"Migrated {migrated} channels")
        
        # Handle remaining batch
        if batch:
            session.add_all(batch)
            session.commit()
            migrated += len(batch)
    
    return migrated

@celery_app.task(bind=True)
def fetch_channel_metadata(self, job_id, channel_ids=None, limit=100):
    """Fetch metadata for channels using YouTube API"""
    session = get_db_session()
    
    try:
        job = session.query(ProcessingJob).filter_by(id=uuid.UUID(job_id)).first()
        if not job:
            raise Exception(f"Job {job_id} not found")
        
        job.start()
        session.commit()
        
        # Get channels to process
        query = session.query(Channel).filter_by(metadata_fetched=False)
        
        if channel_ids:
            query = query.filter(Channel.channel_id.in_(channel_ids))
        
        channels = query.limit(limit).all()
        job.total_items = len(channels)
        session.commit()
        
        youtube_service = YouTubeService()
        processed = 0
        
        for channel in channels:
            try:
                # Fetch metadata from YouTube
                metadata = youtube_service.get_channel_metadata(channel.channel_id)
                
                if metadata:
                    # Update channel with metadata
                    channel.title = metadata.get('title')
                    channel.description = metadata.get('description')
                    channel.subscriber_count = metadata.get('subscriber_count')
                    channel.video_count = metadata.get('video_count')
                    channel.view_count = metadata.get('view_count')
                    channel.country = metadata.get('country')
                    channel.custom_url = metadata.get('custom_url')
                    channel.published_at = metadata.get('published_at')
                    channel.thumbnail_url = metadata.get('thumbnail_url')
                    channel.banner_url = metadata.get('banner_url')
                    channel.keywords = metadata.get('keywords', [])
                    channel.topic_categories = metadata.get('topic_categories', [])
                    
                    # Detect language from description
                    if channel.description:
                        try:
                            channel.language = detect(channel.description)
                        except:
                            channel.language = None
                    
                    channel.metadata_fetched = True
                    channel.last_updated = datetime.utcnow()
                
                processed += 1
                job.update_progress(processed)
                session.commit()
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Failed to fetch metadata for {channel.channel_id}: {str(e)}")
                continue
        
        job.complete()
        session.commit()
        
        logger.info(f"Metadata fetch completed: {processed}/{len(channels)} channels processed")
        return {'status': 'completed', 'processed_count': processed}
        
    except Exception as e:
        logger.error(f"Metadata fetch failed: {str(e)}")
        job.fail(str(e))
        session.commit()
        return {'status': 'failed', 'error': str(e)}
    
    finally:
        session.close()

@celery_app.task(bind=True)
def fetch_channel_videos(self, job_id, channel_ids=None, videos_per_channel=50, limit=100):
    """Fetch recent videos for channels"""
    session = get_db_session()
    
    try:
        job = session.query(ProcessingJob).filter_by(id=uuid.UUID(job_id)).first()
        if not job:
            raise Exception(f"Job {job_id} not found")
        
        job.start()
        session.commit()
        
        # Get channels to process
        query = session.query(Channel).filter_by(videos_fetched=False)
        
        if channel_ids:
            query = query.filter(Channel.channel_id.in_(channel_ids))
        
        channels = query.limit(limit).all()
        job.total_items = len(channels)
        session.commit()
        
        youtube_service = YouTubeService()
        processed = 0
        
        for channel in channels:
            try:
                # Fetch videos from YouTube
                videos = youtube_service.get_channel_videos(
                    channel.channel_id, 
                    max_results=videos_per_channel
                )
                
                # Store videos
                for video_data in videos:
                    # Check if video already exists
                    existing_video = session.query(Video).filter_by(
                        video_id=video_data['video_id']
                    ).first()
                    
                    if not existing_video:
                        video = Video(
                            video_id=video_data['video_id'],
                            channel_id=channel.id,
                            channel_external_id=channel.channel_id,
                            title=video_data.get('title'),
                            description=video_data.get('description'),
                            published_at=video_data.get('published_at'),
                            duration=video_data.get('duration'),
                            view_count=video_data.get('view_count'),
                            like_count=video_data.get('like_count'),
                            comment_count=video_data.get('comment_count'),
                            thumbnail_url=video_data.get('thumbnail_url'),
                            tags=video_data.get('tags', []),
                            category_id=video_data.get('category_id')
                        )
                        
                        # Detect language from video title/description
                        text_for_detection = (video_data.get('title', '') + ' ' + 
                                            video_data.get('description', '')).strip()
                        if text_for_detection:
                            try:
                                video.language = detect(text_for_detection)
                            except:
                                video.language = None
                        
                        session.add(video)
                
                channel.videos_fetched = True
                channel.last_updated = datetime.utcnow()
                
                processed += 1
                job.update_progress(processed)
                session.commit()
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Failed to fetch videos for {channel.channel_id}: {str(e)}")
                continue
        
        job.complete()
        session.commit()
        
        logger.info(f"Video fetch completed: {processed}/{len(channels)} channels processed")
        return {'status': 'completed', 'processed_count': processed}
        
    except Exception as e:
        logger.error(f"Video fetch failed: {str(e)}")
        job.fail(str(e))
        session.commit()
        return {'status': 'failed', 'error': str(e)}
    
    finally:
        session.close()

@celery_app.task(bind=True)
def discover_related_channels(self, job_id, source_channel_ids=None, discovery_methods=None, limit=50):
    """Discover related channels using external services"""
    session = get_db_session()
    
    try:
        job = session.query(ProcessingJob).filter_by(id=uuid.UUID(job_id)).first()
        if not job:
            raise Exception(f"Job {job_id} not found")
        
        job.start()
        session.commit()
        
        # Get channels to process
        query = session.query(Channel).filter_by(discovery_processed=False)
        
        if source_channel_ids:
            query = query.filter(Channel.channel_id.in_(source_channel_ids))
        
        channels = query.limit(limit).all()
        job.total_items = len(channels)
        session.commit()
        
        discovery_service = ExternalChannelDiscovery()
        processed = 0
        new_channels_found = 0
        
        for channel in channels:
            try:
                # Use multiple discovery methods
                methods = discovery_methods or [
                    'related_channels', 
                    'similar_content', 
                    'youtube_featured',
                    'youtube_collaborations'
                ]
                
                for method in methods:
                    try:
                        discovered = discovery_service.discover_channels(
                            channel.channel_id, 
                            method=method
                        )
                        
                        for discovery in discovered:
                            # Record discovery
                            existing_discovery = session.query(ChannelDiscovery).filter_by(
                                source_channel_id=channel.id,
                                discovered_channel_id=discovery['channel_id'],
                                discovery_method=method
                            ).first()
                            
                            if not existing_discovery:
                                # Check if discovered channel already exists
                                existing_channel = session.query(Channel).filter_by(
                                    channel_id=discovery['channel_id']
                                ).first()
                                
                                channel_discovery = ChannelDiscovery(
                                    source_channel_id=channel.id,
                                    discovered_channel_id=discovery['channel_id'],
                                    discovery_method=method,
                                    service_name=discovery.get('service', 'unknown'),
                                    confidence_score=discovery.get('confidence', 0.0),
                                    already_exists=existing_channel is not None
                                )
                                session.add(channel_discovery)
                                
                                # Add new channel if it doesn't exist
                                if not existing_channel:
                                    new_channel = Channel(
                                        channel_id=discovery['channel_id'],
                                        title=discovery.get('title', ''),
                                        source='discovery',
                                        discovered_from=channel.id
                                    )
                                    session.add(new_channel)
                                    new_channels_found += 1
                        
                        # Rate limiting between methods
                        time.sleep(random.uniform(1, 3))
                        
                    except Exception as e:
                        logger.error(f"Discovery method {method} failed for {channel.channel_id}: {str(e)}")
                        continue
                
                channel.discovery_processed = True
                channel.last_updated = datetime.utcnow()
                
                processed += 1
                job.update_progress(processed)
                session.commit()
                
                # Rate limiting between channels
                time.sleep(random.uniform(2, 5))
                
            except Exception as e:
                logger.error(f"Failed to discover channels for {channel.channel_id}: {str(e)}")
                continue
        
        job.complete()
        session.commit()
        
        logger.info(f"Channel discovery completed: {processed}/{len(channels)} channels processed, {new_channels_found} new channels found")
        return {
            'status': 'completed', 
            'processed_count': processed,
            'new_channels_found': new_channels_found
        }
        
    except Exception as e:
        logger.error(f"Channel discovery failed: {str(e)}")
        job.fail(str(e))
        session.commit()
        return {'status': 'failed', 'error': str(e)}
    
    finally:
        session.close()

@celery_app.task
def reset_api_quotas():
    """Reset API quotas for keys that have exceeded their daily limit"""
    session = get_db_session()
    
    try:
        # Reset quotas for keys where reset_date is not today
        today = datetime.utcnow().date()
        keys_to_reset = session.query(APIKey).filter(
            APIKey.quota_reset_date < today
        ).all()
        
        for key in keys_to_reset:
            key.reset_quota()
            logger.info(f"Reset quota for API key: {key.key_name}")
        
        session.commit()
        logger.info(f"Reset quotas for {len(keys_to_reset)} API keys")
        
    except Exception as e:
        logger.error(f"Failed to reset API quotas: {str(e)}")
    finally:
        session.close()

@celery_app.task
def cleanup_old_jobs():
    """Clean up old completed/failed jobs"""
    session = get_db_session()
    
    try:
        # Delete jobs older than 7 days
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        old_jobs = session.query(ProcessingJob).filter(
            ProcessingJob.created_at < cutoff_date,
            ProcessingJob.status.in_(['completed', 'failed'])
        ).all()
        
        for job in old_jobs:
            session.delete(job)
        
        session.commit()
        logger.info(f"Cleaned up {len(old_jobs)} old jobs")
        
    except Exception as e:
        logger.error(f"Failed to cleanup old jobs: {str(e)}")
    finally:
        session.close()

@celery_app.task(bind=True)
def batch_process_channels(self, job_id, operation, batch_size=1000, total_limit=None):
    """
    High-performance batch processing for millions of channels
    Operations: 'metadata', 'videos', 'discovery'
    """
    session = get_db_session()
    
    try:
        job = session.query(ProcessingJob).filter_by(id=uuid.UUID(job_id)).first()
        if not job:
            raise Exception(f"Job {job_id} not found")
        
        job.start()
        session.commit()
        
        logger.info(f"Starting batch processing: {operation} with batch size {batch_size}")
        
        # Get total count for progress tracking
        if operation == 'metadata':
            total_count = session.query(Channel).filter_by(metadata_fetched=False).count()
        elif operation == 'videos':
            total_count = session.query(Channel).filter_by(
                metadata_fetched=True, videos_fetched=False
            ).count()
        elif operation == 'discovery':
            total_count = session.query(Channel).filter_by(discovery_processed=False).count()
        else:
            raise Exception(f"Unknown operation: {operation}")
        
        # Apply limit if specified
        if total_limit and total_limit < total_count:
            total_count = total_limit
        
        job.total_items = total_count
        session.commit()
        
        if total_count == 0:
            job.complete()
            session.commit()
            return {'status': 'completed', 'message': 'No channels to process'}
        
        processed = 0
        batch_number = 1
        
        while processed < total_count:
            # Calculate remaining items for this batch
            remaining = total_count - processed
            current_batch_size = min(batch_size, remaining)
            
            try:
                logger.info(f"Processing batch {batch_number}: {current_batch_size} channels")
                
                if operation == 'metadata':
                    batch_result = process_metadata_batch(current_batch_size, session)
                elif operation == 'videos':
                    batch_result = process_videos_batch(current_batch_size, session)
                elif operation == 'discovery':
                    batch_result = process_discovery_batch(current_batch_size, session)
                
                processed += batch_result.get('processed', 0)
                job.update_progress(processed)
                session.commit()
                
                # Progress reporting
                progress_percent = (processed / total_count) * 100
                logger.info(f"Batch {batch_number} completed. Progress: {processed}/{total_count} ({progress_percent:.1f}%)")
                
                # Rate limiting between batches
                time.sleep(random.uniform(1, 3))
                batch_number += 1
                
            except Exception as e:
                logger.error(f"Batch {batch_number} failed: {str(e)}")
                # Continue with next batch instead of failing entire job
                processed += current_batch_size
                continue
        
        job.complete()
        session.commit()
        
        logger.info(f"Batch processing completed: {processed} channels processed")
        return {
            'status': 'completed', 
            'total_processed': processed,
            'batches_completed': batch_number - 1
        }
        
    except Exception as e:
        logger.error(f"Batch processing failed: {str(e)}")
        job.fail(str(e))
        session.commit()
        return {'status': 'failed', 'error': str(e)}
    
    finally:
        session.close()

def process_metadata_batch(batch_size, session):
    """Process a batch of channels for metadata fetching"""
    try:
        channels = session.query(Channel).filter_by(metadata_fetched=False).limit(batch_size).all()
        
        youtube_service = YouTubeService()
        processed = 0
        
        for channel in channels:
            try:
                metadata = youtube_service.get_channel_metadata(channel.channel_id)
                
                if metadata:
                    # Update channel with metadata
                    channel.title = metadata.get('title', channel.title)
                    channel.description = metadata.get('description')
                    channel.subscriber_count = metadata.get('subscriber_count', 0)
                    channel.video_count = metadata.get('video_count', 0)
                    channel.view_count = metadata.get('view_count', 0)
                    channel.country = metadata.get('country')
                    channel.custom_url = metadata.get('custom_url')
                    channel.published_at = metadata.get('published_at')
                    channel.thumbnail_url = metadata.get('thumbnail_url')
                    channel.banner_url = metadata.get('banner_url')
                    channel.keywords = metadata.get('keywords', [])
                    channel.topic_categories = metadata.get('topic_categories', [])
                    
                    # Language detection
                    if channel.description:
                        try:
                            channel.language = detect(channel.description)
                        except:
                            channel.language = None
                    
                    channel.metadata_fetched = True
                    channel.last_updated = datetime.utcnow()
                
                processed += 1
                
                # Commit every 10 channels to avoid large transactions
                if processed % 10 == 0:
                    session.commit()
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Failed to process channel {channel.channel_id}: {str(e)}")
                continue
        
        # Final commit
        session.commit()
        youtube_service.close()
        
        return {'processed': processed}
        
    except Exception as e:
        logger.error(f"Metadata batch processing failed: {str(e)}")
        return {'processed': 0, 'error': str(e)}

def process_videos_batch(batch_size, session):
    """Process a batch of channels for video fetching"""
    try:
        channels = session.query(Channel).filter_by(
            metadata_fetched=True, 
            videos_fetched=False
        ).limit(batch_size).all()
        
        youtube_service = YouTubeService()
        processed = 0
        
        for channel in channels:
            try:
                videos_per_channel = int(os.getenv('MAX_VIDEOS_PER_CHANNEL', 50))
                videos = youtube_service.get_channel_videos(channel.channel_id, max_results=videos_per_channel)
                
                video_count = 0
                for video_data in videos:
                    # Check if video already exists
                    existing_video = session.query(Video).filter_by(
                        video_id=video_data['video_id']
                    ).first()
                    
                    if not existing_video:
                        video = Video(
                            video_id=video_data['video_id'],
                            channel_id=channel.id,
                            channel_external_id=channel.channel_id,
                            title=video_data.get('title'),
                            description=video_data.get('description'),
                            published_at=video_data.get('published_at'),
                            duration=video_data.get('duration'),
                            view_count=video_data.get('view_count'),
                            like_count=video_data.get('like_count'),
                            comment_count=video_data.get('comment_count'),
                            thumbnail_url=video_data.get('thumbnail_url'),
                            tags=video_data.get('tags', []),
                            category_id=video_data.get('category_id')
                        )
                        
                        # Language detection
                        text_for_detection = (video_data.get('title', '') + ' ' + 
                                            video_data.get('description', '')).strip()
                        if text_for_detection:
                            try:
                                video.language = detect(text_for_detection)
                            except:
                                video.language = None
                        
                        session.add(video)
                        video_count += 1
                
                channel.videos_fetched = True
                channel.last_updated = datetime.utcnow()
                processed += 1
                
                # Commit every 5 channels to manage transaction size
                if processed % 5 == 0:
                    session.commit()
                
                # Rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Failed to fetch videos for {channel.channel_id}: {str(e)}")
                continue
        
        session.commit()
        youtube_service.close()
        
        return {'processed': processed}
        
    except Exception as e:
        logger.error(f"Videos batch processing failed: {str(e)}")
        return {'processed': 0, 'error': str(e)}

def process_discovery_batch(batch_size, session):
    """Process a batch of channels for discovery"""
    try:
        channels = session.query(Channel).filter_by(discovery_processed=False).limit(batch_size).all()
        
        discovery_service = ExternalChannelDiscovery()
        processed = 0
        new_channels_found = 0
        
        for channel in channels:
            try:
                # Use multiple discovery methods
                methods = ['youtube_featured', 'similar_content', 'related_channels']
                
                for method in methods:
                    try:
                        discovered = discovery_service.discover_channels(
                            channel.channel_id, 
                            method=method
                        )
                        
                        for discovery in discovered:
                            # Record discovery
                            existing_discovery = session.query(ChannelDiscovery).filter_by(
                                source_channel_id=channel.id,
                                discovered_channel_id=discovery['channel_id'],
                                discovery_method=method
                            ).first()
                            
                            if not existing_discovery:
                                # Check if discovered channel already exists
                                existing_channel = session.query(Channel).filter_by(
                                    channel_id=discovery['channel_id']
                                ).first()
                                
                                channel_discovery = ChannelDiscovery(
                                    source_channel_id=channel.id,
                                    discovered_channel_id=discovery['channel_id'],
                                    discovery_method=method,
                                    service_name=discovery.get('service', 'unknown'),
                                    confidence_score=discovery.get('confidence', 0.0),
                                    already_exists=existing_channel is not None
                                )
                                session.add(channel_discovery)
                                
                                # Add new channel if it doesn't exist
                                if not existing_channel:
                                    new_channel = Channel(
                                        channel_id=discovery['channel_id'],
                                        title=discovery.get('title', ''),
                                        source='discovery',
                                        discovered_from=channel.id
                                    )
                                    session.add(new_channel)
                                    new_channels_found += 1
                        
                        # Rate limiting between methods
                        time.sleep(random.uniform(2, 4))
                        
                    except Exception as e:
                        logger.error(f"Discovery method {method} failed for {channel.channel_id}: {str(e)}")
                        continue
                
                channel.discovery_processed = True
                channel.last_updated = datetime.utcnow()
                processed += 1
                
                # Commit every 3 channels (discovery creates many records)
                if processed % 3 == 0:
                    session.commit()
                
                # Rate limiting between channels
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                logger.error(f"Failed to discover channels for {channel.channel_id}: {str(e)}")
                continue
        
        session.commit()
        discovery_service.close()
        
        return {'processed': processed, 'new_channels_found': new_channels_found}
        
    except Exception as e:
        logger.error(f"Discovery batch processing failed: {str(e)}")
        return {'processed': 0, 'error': str(e)}

@celery_app.task
def monitor_system_health():
    """Monitor system health and performance"""
    try:
        from app.redis_config import test_redis_connection
        
        # Test Redis connection
        redis_status = test_redis_connection()
        
        # Test database connection
        session = get_db_session()
        try:
            session.execute(text("SELECT 1"))
            db_status = {'status': 'success'}
        except Exception as e:
            db_status = {'status': 'error', 'message': str(e)}
        finally:
            session.close()
        
        # Log health status
        if redis_status['status'] == 'success' and db_status['status'] == 'success':
            logger.info("✅ System health check passed")
        else:
            logger.error(f"❌ System health check failed: Redis={redis_status['status']}, DB={db_status['status']}")
        
        return {
            'redis': redis_status,
            'database': db_status,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health monitoring failed: {str(e)}")
        return {'status': 'error', 'message': str(e)}