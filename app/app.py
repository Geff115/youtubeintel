from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
import uuid
from datetime import datetime

load_dotenv()

# Create Flask app
app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost:5432/youtube_channels')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize database
from database import init_db
db = init_db(app)

# Import Redis configuration
from redis_config import test_redis_connection

# Import models after database is initialized
from models import Channel, Video, APIKey, ProcessingJob, ChannelDiscovery

# Import tasks after models are set up
from tasks import (
    migrate_channel_data, 
    fetch_channel_metadata, 
    fetch_channel_videos,
    discover_related_channels,
    batch_process_channels,
    celery_app
)

# Routes
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    try:
        stats = {
            'total_channels': Channel.query.count(),
            'channels_with_metadata': Channel.query.filter_by(metadata_fetched=True).count(),
            'channels_with_videos': Channel.query.filter_by(videos_fetched=True).count(),
            'total_videos': Video.query.count(),
            'active_api_keys': APIKey.query.filter_by(is_active=True).count(),
            'pending_jobs': ProcessingJob.query.filter_by(status='pending').count(),
            'running_jobs': ProcessingJob.query.filter_by(status='running').count()
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels', methods=['GET'])
def list_channels():
    """List channels with pagination"""
    try:
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 20)), 100)
        
        channels = Channel.query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'channels': [channel.to_dict() for channel in channels.items],
            'total': channels.total,
            'pages': channels.pages,
            'current_page': channels.page,
            'per_page': per_page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/api-keys', methods=['GET'])
def list_api_keys():
    """List API keys (masked for security)"""
    try:
        keys = APIKey.query.all()
        return jsonify([{
            'id': str(key.id),
            'key_name': key.key_name,
            'service': key.service,
            'api_key': f"{key.api_key[:8]}...{key.api_key[-4:]}",
            'quota_limit': key.quota_limit,
            'quota_used': key.quota_used,
            'is_active': key.is_active,
            'last_used': key.last_used.isoformat() if key.last_used else None
        } for key in keys])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List processing jobs"""
    try:
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        query = ProcessingJob.query
        if status:
            query = query.filter_by(status=status)
        
        jobs = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()
        
        return jsonify([{
            'job_id': str(job.id),
            'job_type': job.job_type,
            'status': job.status,
            'total_items': job.total_items,
            'processed_items': job.processed_items,
            'created_at': job.created_at.isoformat(),
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None
        } for job in jobs])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get processing job status"""
    try:
        job = ProcessingJob.query.get(uuid.UUID(job_id))
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify({
            'job_id': str(job.id),
            'job_type': job.job_type,
            'status': job.status,
            'total_items': job.total_items,
            'processed_items': job.processed_items,
            'progress': (job.processed_items / job.total_items * 100) if job.total_items else 0,
            'error_message': job.error_message,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'created_at': job.created_at.isoformat()
        })
    except ValueError:
        return jsonify({'error': 'Invalid job ID format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-youtube', methods=['POST'])
def test_youtube_connection():
    """Test YouTube API connection"""
    try:
        # Get API keys
        api_keys = APIKey.query.filter_by(service='youtube', is_active=True).all()
        
        if not api_keys:
            return jsonify({'error': 'No active YouTube API keys found'}), 400
        
        # Test the first API key
        api_key = api_keys[0]
        
        from googleapiclient.discovery import build
        youtube = build('youtube', 'v3', developerKey=api_key.api_key)
        
        # Simple test - get a channel by ID
        test_channel_id = 'UCBJycsmduvYEL83R_U4JriQ'  # MKBHD
        
        request = youtube.channels().list(
            part='snippet,statistics',
            id=test_channel_id
        )
        response = request.execute()
        
        if response.get('items'):
            channel_data = response['items'][0]
            return jsonify({
                'success': True,
                'message': 'YouTube API connection successful',
                'test_channel': {
                    'id': test_channel_id,
                    'title': channel_data['snippet']['title'],
                    'subscriber_count': channel_data['statistics'].get('subscriberCount', 0)
                },
                'api_key_used': api_key.key_name
            })
        else:
            return jsonify({'error': 'No data returned from YouTube API'}), 400
            
    except Exception as e:
        return jsonify({'error': f'YouTube API test failed: {str(e)}'}), 500

@app.route('/api/fetch-sample-metadata', methods=['POST'])
def fetch_sample_metadata():
    """Fetch metadata for sample channels"""
    try:
        from googleapiclient.discovery import build
        
        # Get API key
        api_key = APIKey.query.filter_by(service='youtube', is_active=True).first()
        if not api_key:
            return jsonify({'error': 'No active YouTube API keys found'}), 400
        
        youtube = build('youtube', 'v3', developerKey=api_key.api_key)
        
        # Get sample channels that don't have metadata yet
        channels = Channel.query.filter_by(metadata_fetched=False).limit(3).all()
        
        if not channels:
            return jsonify({'message': 'All sample channels already have metadata', 'updated': 0})
        
        updated_count = 0
        results = []
        
        for channel in channels:
            try:
                # Fetch metadata from YouTube
                request = youtube.channels().list(
                    part='snippet,statistics,brandingSettings',
                    id=channel.channel_id
                )
                response = request.execute()
                
                if response.get('items'):
                    channel_data = response['items'][0]
                    snippet = channel_data.get('snippet', {})
                    statistics = channel_data.get('statistics', {})
                    branding = channel_data.get('brandingSettings', {}).get('channel', {})
                    
                    # Update channel with metadata
                    channel.title = snippet.get('title', channel.title)
                    channel.description = snippet.get('description')
                    channel.subscriber_count = int(statistics.get('subscriberCount', 0))
                    channel.video_count = int(statistics.get('videoCount', 0))
                    channel.view_count = int(statistics.get('viewCount', 0))
                    channel.country = snippet.get('country')
                    channel.custom_url = snippet.get('customUrl')
                    channel.thumbnail_url = snippet.get('thumbnails', {}).get('high', {}).get('url')
                    
                    if snippet.get('publishedAt'):
                        try:
                            published_at = datetime.fromisoformat(
                                snippet['publishedAt'].replace('Z', '+00:00')
                            )
                            channel.published_at = published_at
                        except:
                            pass
                    
                    # Extract keywords
                    keywords = branding.get('keywords', '')
                    if keywords:
                        channel.keywords = [k.strip() for k in keywords.split(',')]
                    
                    channel.metadata_fetched = True
                    channel.last_updated = datetime.utcnow()
                    
                    # Update API key usage
                    api_key.quota_used += 1
                    api_key.last_used = datetime.utcnow()
                    
                    updated_count += 1
                    results.append({
                        'channel_id': channel.channel_id,
                        'title': channel.title,
                        'subscriber_count': channel.subscriber_count,
                        'status': 'updated'
                    })
                    
                else:
                    results.append({
                        'channel_id': channel.channel_id,
                        'status': 'not_found'
                    })
                    
            except Exception as e:
                results.append({
                    'channel_id': channel.channel_id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Save all changes
        db.session.commit()
        
        return jsonify({
            'message': f'Updated metadata for {updated_count} channels',
            'updated': updated_count,
            'results': results,
            'api_key_used': api_key.key_name,
            'quota_used': api_key.quota_used
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Metadata fetch failed: {str(e)}'}), 500

@app.route('/api/fetch-sample-videos', methods=['POST'])
def fetch_sample_videos():
    """Fetch videos for sample channels"""
    try:
        from googleapiclient.discovery import build
        
        # Get API key
        api_key = APIKey.query.filter_by(service='youtube', is_active=True).first()
        if not api_key:
            return jsonify({'error': 'No active YouTube API keys found'}), 400
        
        youtube = build('youtube', 'v3', developerKey=api_key.api_key)
        
        # Get sample channels that have metadata but no videos
        channels = Channel.query.filter_by(
            metadata_fetched=True, 
            videos_fetched=False
        ).limit(2).all()
        
        if not channels:
            return jsonify({'message': 'No channels ready for video fetching', 'processed': 0})
        
        processed_count = 0
        results = []
        
        for channel in channels:
            try:
                # Get channel's uploads playlist
                channel_request = youtube.channels().list(
                    part='contentDetails',
                    id=channel.channel_id
                )
                channel_response = channel_request.execute()
                
                if not channel_response.get('items'):
                    continue
                
                uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
                
                # Get recent videos from uploads playlist
                playlist_request = youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist_id,
                    maxResults=10  # Limit to 10 videos for testing
                )
                playlist_response = playlist_request.execute()
                
                video_count = 0
                for item in playlist_response.get('items', []):
                    video_id = item['snippet']['resourceId']['videoId']
                    
                    # Check if video already exists
                    existing_video = Video.query.filter_by(video_id=video_id).first()
                    if existing_video:
                        continue
                    
                    # Create new video record
                    video = Video(
                        video_id=video_id,
                        channel_id=channel.id,
                        channel_external_id=channel.channel_id,
                        title=item['snippet'].get('title'),
                        description=item['snippet'].get('description'),
                        thumbnail_url=item['snippet'].get('thumbnails', {}).get('high', {}).get('url')
                    )
                    
                    # Parse published date
                    if item['snippet'].get('publishedAt'):
                        try:
                            published_at = datetime.fromisoformat(
                                item['snippet']['publishedAt'].replace('Z', '+00:00')
                            )
                            video.published_at = published_at
                        except:
                            pass
                    
                    db.session.add(video)
                    video_count += 1
                
                channel.videos_fetched = True
                channel.last_updated = datetime.utcnow()
                
                # Update API key usage
                api_key.quota_used += 2  # 1 for channel, 1 for playlist
                api_key.last_used = datetime.utcnow()
                
                processed_count += 1
                results.append({
                    'channel_id': channel.channel_id,
                    'title': channel.title,
                    'videos_added': video_count,
                    'status': 'success'
                })
                
            except Exception as e:
                results.append({
                    'channel_id': channel.channel_id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Save all changes
        db.session.commit()
        
        return jsonify({
            'message': f'Processed videos for {processed_count} channels',
            'processed': processed_count,
            'results': results,
            'api_key_used': api_key.key_name,
            'quota_used': api_key.quota_used
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Video fetch failed: {str(e)}'}), 500

@app.route('/api/add-sample-channels', methods=['POST'])
def add_sample_channels():
    """Add more sample channels for testing"""
    try:
        # Some popular tech channels for testing
        sample_channels = [
            {'channel_id': 'UCsgp0TTPJdAqkaGMqq-HJ9w', 'title': 'MrBeast Gaming', 'description': 'MrBeast Gaming Channel'},
            {'channel_id': 'UC-lHJZR3Gqxm24_Vd_AJ5Yw', 'title': 'PewDiePie', 'description': 'Gaming and Entertainment'},
            {'channel_id': 'UCUZHFZ9jIKrLroW8LcyJEQQ', 'title': 'YouTube Creators', 'description': 'Official YouTube Creators Channel'},
            {'channel_id': 'UCYfdidRxbB8Qhf0Nx7ioOYw', 'title': 'Veritasium', 'description': 'Science and Engineering Videos'},
            {'channel_id': 'UCsooa4yRKGN_zEE8iknghZA', 'title': 'TED-Ed', 'description': 'Educational Videos'}
        ]
        
        added_count = 0
        results = []
        
        for channel_data in sample_channels:
            # Check if channel already exists
            existing = Channel.query.filter_by(channel_id=channel_data['channel_id']).first()
            
            if not existing:
                channel = Channel(
                    channel_id=channel_data['channel_id'],
                    title=channel_data['title'],
                    description=channel_data['description'],
                    source='sample_added'
                )
                db.session.add(channel)
                added_count += 1
                results.append({
                    'channel_id': channel_data['channel_id'],
                    'title': channel_data['title'],
                    'status': 'added'
                })
            else:
                results.append({
                    'channel_id': channel_data['channel_id'],
                    'title': channel_data['title'],
                    'status': 'already_exists'
                })
        
        db.session.commit()
        
        return jsonify({
            'message': f'Added {added_count} new sample channels',
            'added': added_count,
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to add sample channels: {str(e)}'}), 500

@app.route('/api/redis-test', methods=['GET'])
def test_redis():
    """Test Redis connection (local or UPSTASH)"""
    try:
        result = test_redis_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/batch-metadata', methods=['POST'])
def start_batch_metadata():
    """Start batch metadata processing for large volumes"""
    try:
        data = request.get_json() or {}
        batch_size = data.get('batch_size', 1000)
        total_limit = data.get('total_limit')  # Optional limit
        
        # Create processing job
        job = ProcessingJob(
            job_type='batch_metadata',
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = batch_process_channels.delay(
            job_id=str(job.id),
            operation='metadata',
            batch_size=batch_size,
            total_limit=total_limit
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Batch metadata processing started with batch size {batch_size}',
            'estimated_batches': (total_limit or 'unknown') // batch_size if total_limit else 'unknown'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start batch processing: {str(e)}'}), 500

@app.route('/api/batch-videos', methods=['POST'])
def start_batch_videos():
    """Start batch video processing for large volumes"""
    try:
        data = request.get_json() or {}
        batch_size = data.get('batch_size', 500)  # Smaller batches for videos
        total_limit = data.get('total_limit')
        
        # Create processing job
        job = ProcessingJob(
            job_type='batch_videos',
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = batch_process_channels.delay(
            job_id=str(job.id),
            operation='videos',
            batch_size=batch_size,
            total_limit=total_limit
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Batch video processing started with batch size {batch_size}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start batch processing: {str(e)}'}), 500

@app.route('/api/batch-discovery', methods=['POST'])
def start_batch_discovery():
    """Start batch discovery processing for large volumes"""
    try:
        data = request.get_json() or {}
        batch_size = data.get('batch_size', 100)  # Smaller batches for discovery
        total_limit = data.get('total_limit')
        
        # Create processing job
        job = ProcessingJob(
            job_type='batch_discovery',
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = batch_process_channels.delay(
            job_id=str(job.id),
            operation='discovery',
            batch_size=batch_size,
            total_limit=total_limit
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Batch discovery processing started with batch size {batch_size}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start batch processing: {str(e)}'}), 500

@app.route('/api/migrate', methods=['POST'])
def start_migration():
    """Start channel data migration from existing sources"""
    try:
        data = request.get_json() or {}
        source_type = data.get('source_type', 'csv')  # csv, json, mysql
        source_path = data.get('source_path', '')
        batch_size = data.get('batch_size', 5000)  # Larger batches for migration
        
        if not source_path:
            return jsonify({'error': 'source_path is required'}), 400
        
        # Create processing job
        job = ProcessingJob(
            job_type='migration',
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = migrate_channel_data.delay(
            job_id=str(job.id),
            source_type=source_type,
            source_path=source_path,
            batch_size=batch_size
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Migration started for {source_type} source with batch size {batch_size}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start migration: {str(e)}'}), 500

@app.route('/api/legacy-fetch-metadata', methods=['POST'])
def start_legacy_metadata_fetch():
    """Start legacy metadata fetch (original implementation)"""
    try:
        data = request.get_json() or {}
        channel_ids = data.get('channel_ids', [])
        limit = data.get('limit', 1000)
        
        # Create processing job
        job = ProcessingJob(
            job_type='metadata_fetch',
            status='pending',
            total_items=limit
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = fetch_channel_metadata.delay(
            job_id=str(job.id),
            channel_ids=channel_ids,
            limit=limit
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Legacy metadata fetch started for up to {limit} channels'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start metadata fetch: {str(e)}'}), 500

@app.route('/api/system-status', methods=['GET'])
def get_system_status():
    """Get comprehensive system status"""
    try:
        # Get basic stats
        stats = {
            'total_channels': Channel.query.count(),
            'channels_with_metadata': Channel.query.filter_by(metadata_fetched=True).count(),
            'channels_with_videos': Channel.query.filter_by(videos_fetched=True).count(),
            'total_videos': Video.query.count(),
            'active_api_keys': APIKey.query.filter_by(is_active=True).count(),
            'pending_jobs': ProcessingJob.query.filter_by(status='pending').count(),
            'running_jobs': ProcessingJob.query.filter_by(status='running').count(),
            'completed_jobs_today': ProcessingJob.query.filter(
                ProcessingJob.status == 'completed',
                ProcessingJob.completed_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            ).count()
        }
        
        # Test Redis connection
        redis_status = test_redis_connection()
        
        # Get API key usage
        api_keys = APIKey.query.filter_by(is_active=True).all()
        api_key_status = []
        for key in api_keys:
            api_key_status.append({
                'key_name': key.key_name,
                'quota_used': key.quota_used,
                'quota_limit': key.quota_limit,
                'usage_percentage': (key.quota_used / key.quota_limit * 100) if key.quota_limit > 0 else 0,
                'last_used': key.last_used.isoformat() if key.last_used else None
            })
        
        # Get recent job activity
        recent_jobs = ProcessingJob.query.order_by(
            ProcessingJob.created_at.desc()
        ).limit(10).all()
        
        job_activity = []
        for job in recent_jobs:
            job_activity.append({
                'job_id': str(job.id),
                'job_type': job.job_type,
                'status': job.status,
                'progress': (job.processed_items / job.total_items * 100) if job.total_items else 0,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None
            })
        
        return jsonify({
            'stats': stats,
            'redis_status': redis_status,
            'api_keys': api_key_status,
            'recent_jobs': job_activity,
            'environment': os.getenv('ENVIRONMENT', 'development'),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get system status: {str(e)}'}), 500

@app.route('/api/bulk-add-channels', methods=['POST'])
def bulk_add_channels():
    """Add channels in bulk from JSON data"""
    try:
        data = request.get_json() or {}
        channels_data = data.get('channels', [])
        source = data.get('source', 'bulk_upload')
        
        if not channels_data:
            return jsonify({'error': 'No channels data provided'}), 400
        
        added_count = 0
        skipped_count = 0
        results = []
        
        # Process in batches to avoid memory issues
        batch_size = 1000
        for i in range(0, len(channels_data), batch_size):
            batch = channels_data[i:i + batch_size]
            
            for channel_data in batch:
                channel_id = channel_data.get('channel_id')
                if not channel_id:
                    continue
                
                # Check if channel already exists
                existing = Channel.query.filter_by(channel_id=channel_id).first()
                
                if not existing:
                    channel = Channel(
                        channel_id=channel_id,
                        title=channel_data.get('title', ''),
                        description=channel_data.get('description', ''),
                        source=source
                    )
                    db.session.add(channel)
                    added_count += 1
                    results.append({
                        'channel_id': channel_id,
                        'status': 'added'
                    })
                else:
                    skipped_count += 1
                    results.append({
                        'channel_id': channel_id,
                        'status': 'already_exists'
                    })
            
            # Commit batch
            db.session.commit()
        
        return jsonify({
            'message': f'Bulk upload completed: {added_count} added, {skipped_count} skipped',
            'added': added_count,
            'skipped': skipped_count,
            'total_processed': len(channels_data),
            'results': results[:100]  # Return first 100 results
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Bulk add failed: {str(e)}'}), 500

@app.route('/api/worker-status', methods=['GET'])
def get_worker_status():
    """Get Celery worker status"""
    try:
        # Get active workers
        inspect = celery_app.control.inspect()
        
        # Get worker stats
        stats = inspect.stats()
        active_tasks = inspect.active()
        scheduled_tasks = inspect.scheduled()
        
        worker_info = []
        if stats:
            for worker_name, worker_stats in stats.items():
                worker_info.append({
                    'worker': worker_name,
                    'status': 'online',
                    'processed_tasks': worker_stats.get('total', {}).get('tasks.total', 0),
                    'active_tasks': len(active_tasks.get(worker_name, [])),
                    'scheduled_tasks': len(scheduled_tasks.get(worker_name, [])),
                    'load_avg': worker_stats.get('rusage', {}).get('utime', 0)
                })
        
        return jsonify({
            'workers': worker_info,
            'total_workers': len(worker_info),
            'broker_url': celery_app.conf.broker_url.replace(celery_app.conf.broker_url.split('@')[0].split('://')[1], '***') if '@' in celery_app.conf.broker_url else celery_app.conf.broker_url,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Failed to get worker status: {str(e)}',
            'workers': [],
            'total_workers': 0
        })


if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
    
    app.run(host='0.0.0.0', port=5000, debug=True)