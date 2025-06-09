from celery import Celery
from celery.signals import worker_ready
import os
from datetime import datetime, timedelta
import json
import csv
import mysql.connector
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import uuid
import logging
from langdetect import detect
import requests
import time
import random

from models import db, Channel, Video, APIKey, ProcessingJob, ChannelDiscovery
from youtube_service import YouTubeService
from external_services import ExternalChannelDiscovery

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery('youtube_processor')
celery_app.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        'tasks.migrate_channel_data': {'queue': 'migration'},
        'tasks.fetch_channel_metadata': {'queue': 'youtube_api'},
        'tasks.fetch_channel_videos': {'queue': 'youtube_api'},
        'tasks.discover_related_channels': {'queue': 'discovery'},
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
    }
)

# Database setup for Celery tasks
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost/youtube_channels?schema=public')
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
                methods = discovery_methods or ['related_channels', 'similar_content']
                
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