from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import uuid
import logging
from datetime import datetime
from payment_service import KorapayService, CREDIT_PACKAGES, get_package_by_credits

load_dotenv()

# Create Flask app
app = Flask(__name__)

# CORS configuration for frontend
CORS(app, origins=[
    
    "http://localhost:3000",  # Local development (frontend)
    "https://youtubeintel-backend.onrender.com",  # Render backend
], supports_credentials=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://youtube:youtube123@localhost:5432/youtube_channels')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize database
from database import init_db
db = init_db(app)

# Import Redis configuration
from redis_config import test_redis_connection

# Import authentication (with proper imports)
from auth import token_required, admin_required, validate_input
from rate_limiter import rate_limit, rate_limiter

# Import models after database is initialized
from models import Channel, Video, APIKey, ProcessingJob, ChannelDiscovery, User, CreditTransaction, UserSession, APIUsageLog

# Import tasks after models are set up
from tasks import (
    migrate_channel_data, 
    fetch_channel_metadata, 
    fetch_channel_videos,
    discover_related_channels,
    batch_process_channels,
    celery_app
)

# Register authentication blueprint
from auth_routes import auth_bp
app.register_blueprint(auth_bp)

# Routes
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '2.0.0',
        'features': {
            'authentication': True,
            'rate_limiting': True,
            'credit_system': True,
            'google_oauth': bool(os.getenv('GOOGLE_CLIENT_ID')),
            'email_service': bool(os.getenv('SMTP_USERNAME') or os.getenv('MAILGUN_API_KEY'))
        }
    })

@app.route('/api/stats', methods=['GET'])
@token_required
@rate_limit(credits_cost=0)
def get_stats():
    """Get system statistics (authenticated)"""
    try:
        # Get user's stats
        user_id = request.current_user['id']
        user = db.session.get(User, user_id)
        
        # Basic system stats (limited for regular users)
        stats = {
            'total_channels': Channel.query.count(),
            'channels_with_metadata': Channel.query.filter_by(metadata_fetched=True).count(),
            'total_videos': Video.query.count(),
            'user_stats': {
                'credits_balance': user.credits_balance,
                'total_credits_purchased': user.total_credits_purchased,
                'current_plan': user.current_plan,
                'api_usage_today': APIUsageLog.query.filter(
                    APIUsageLog.user_id == user_id,
                    APIUsageLog.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                ).count()
            }
        }
        
        # Add admin stats if user is admin
        if user.is_admin:
            stats.update({
                'active_api_keys': APIKey.query.filter_by(is_active=True).count(),
                'pending_jobs': ProcessingJob.query.filter_by(status='pending').count(),
                'running_jobs': ProcessingJob.query.filter_by(status='running').count(),
                'total_users': User.query.count(),
                'active_users_today': User.query.filter(
                    User.last_activity >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                ).count()
            })
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels', methods=['GET'])
@token_required
@rate_limit(credits_cost=1)
def list_channels():
    """List channels with pagination (authenticated)"""
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

@app.route('/api/admin/api-keys', methods=['GET'])
@admin_required
def list_api_keys():
    """List API keys (admin only)"""
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
@token_required
@rate_limit(credits_cost=0)
def list_jobs():
    """List user's processing jobs"""
    try:
        user_id = request.current_user['id']
        user = User.query.get(user_id)
        
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        # Regular users see only their jobs, admins see all
        if user.is_admin:
            query = ProcessingJob.query
        else:
            # For now, show all jobs since we don't have user-specific jobs yet
            # In the future, I might want to add user_id to ProcessingJob model
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
@token_required
@rate_limit(credits_cost=0)
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

@app.route('/api/discover-channels', methods=['POST'])
@token_required
@rate_limit(credits_cost=5)  # 5 credits for channel discovery
def discover_channels():
    """Discover related channels (authenticated with credits)"""
    try:
        data = request.get_json() or {}
        source_channel_ids = data.get('channel_ids', [])
        discovery_methods = data.get('methods', ['related_channels'])
        limit = min(int(data.get('limit', 50)), 200)  # Max 200 channels
        
        if not source_channel_ids:
            return jsonify({'error': 'At least one source channel ID is required'}), 400
        
        # Create processing job
        job = ProcessingJob(
            job_type='channel_discovery',
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = discover_related_channels.delay(
            job_id=str(job.id),
            source_channel_ids=source_channel_ids,
            discovery_methods=discovery_methods,
            limit=limit
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Channel discovery started for {len(source_channel_ids)} source channels',
            'estimated_credits': len(source_channel_ids) * len(discovery_methods),
            'discovery_methods': discovery_methods
        })
        
    except Exception as e:
        logger.error(f"Channel discovery error: {str(e)}")
        return jsonify({'error': f'Failed to start channel discovery: {str(e)}'}), 500

@app.route('/api/fetch-metadata', methods=['POST'])
@token_required
@rate_limit(credits_cost=10)  # 10 credits for metadata fetch
def fetch_metadata():
    """Fetch channel metadata (authenticated with credits)"""
    try:
        data = request.get_json() or {}
        channel_ids = data.get('channel_ids', [])
        limit = min(int(data.get('limit', 100)), 500)  # Max 500 channels
        
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
            'message': f'Metadata fetch started for up to {limit} channels'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start metadata fetch: {str(e)}'}), 500

@app.route('/api/fetch-videos', methods=['POST'])
@token_required
@rate_limit(credits_cost=15)  # 15 credits for video fetch
def fetch_videos():
    """Fetch channel videos (authenticated with credits)"""
    try:
        data = request.get_json() or {}
        channel_ids = data.get('channel_ids', [])
        videos_per_channel = min(int(data.get('videos_per_channel', 50)), 100)
        limit = min(int(data.get('limit', 100)), 200)
        
        # Create processing job
        job = ProcessingJob(
            job_type='video_fetch',
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start async task
        task = fetch_channel_videos.delay(
            job_id=str(job.id),
            channel_ids=channel_ids,
            videos_per_channel=videos_per_channel,
            limit=limit
        )
        
        return jsonify({
            'job_id': str(job.id),
            'task_id': task.id,
            'status': 'started',
            'message': f'Video fetch started for up to {limit} channels'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start video fetch: {str(e)}'}), 500

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
@token_required
@rate_limit(credits_cost=25)  # 25 credits for batch processing
def start_batch_metadata():
    """Start batch metadata processing (authenticated with credits)"""
    try:
        data = request.get_json() or {}
        batch_size = min(int(data.get('batch_size', 1000)), 5000)  # Max 5000 per batch
        total_limit = data.get('total_limit')
        
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
@token_required
@rate_limit(credits_cost=35)  # 35 credits for batch video processing
def start_batch_videos():
    """Start batch video processing (authenticated with credits)"""
    try:
        data = request.get_json() or {}
        batch_size = min(int(data.get('batch_size', 500)), 2000)
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
@token_required
@rate_limit(credits_cost=50)  # 50 credits for batch discovery
def start_batch_discovery():
    """Start batch discovery processing (authenticated with credits)"""
    try:
        data = request.get_json() or {}
        batch_size = min(int(data.get('batch_size', 100)), 500)
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

@app.route('/api/user/profile', methods=['GET'])
@token_required
def get_user_profile():
    """Get user profile information"""
    try:
        user_id = request.current_user['id']
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get usage stats
        usage_stats = rate_limiter.get_current_usage(str(user.id), user.current_plan)
        
        # Get recent API usage
        recent_usage = APIUsageLog.query.filter_by(user_id=user.id).order_by(
            APIUsageLog.created_at.desc()
        ).limit(10).all()
        
        return jsonify({
            'user': user.to_dict(),
            'usage_stats': usage_stats,
            'recent_activity': [log.to_dict() for log in recent_usage]
        })
        
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/profile', methods=['PUT'])
@token_required
@rate_limit(credits_cost=0)
def update_user_profile():
    """Update user profile information"""
    try:
        user_id = request.current_user['id']
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json() or {}
        
        # Update allowed fields
        if 'first_name' in data:
            user.first_name = data['first_name'].strip()
        if 'last_name' in data:
            user.last_name = data['last_name'].strip()
        if 'display_name' in data:
            user.display_name = data['display_name'].strip()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Profile update error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
@admin_required
def get_system_status():
    """Get comprehensive system status (admin only)"""
    try:
        # Get basic stats
        stats = {
            'total_channels': Channel.query.count(),
            'channels_with_metadata': Channel.query.filter_by(metadata_fetched=True).count(),
            'channels_with_videos': Channel.query.filter_by(videos_fetched=True).count(),
            'total_videos': Video.query.count(),
            'total_users': User.query.count(),
            'active_users_today': User.query.filter(
                User.last_activity >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            ).count(),
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
@admin_required
def get_worker_status():
    """Get Celery worker status (admin only)"""
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

@app.route('/api/credit-packages', methods=['GET'])
def get_credit_packages():
    """Get available credit packages (Korapay-friendly)"""
    from payment_service import KORAPAY_PACKAGES
    
    return jsonify({
        'packages': KORAPAY_PACKAGES,
        'free_tier': {
            'credits': 25, 
            'renewable': 'monthly',
            'description': 'Free tier includes 25 credits per month'
        },
        'pricing_notes': {
            'currency': 'USD',
            'channel_discovery': '1 credit per channel',
            'full_analysis': '2 credits per channel (metadata + videos)',
            'batch_processing': '5 credits per 100 channels',
            'payment_info': 'Payments processed in Nigerian Naira (NGN) via Korapay',
            'max_single_purchase': 'Maximum $12.50 per transaction due to payment processor limits'
        },
        'larger_packages': {
            'note': 'For larger credit purchases, please contact us for bank transfer options',
            'email': 'sales@youtubeintel.com',
            'enterprise_pricing': 'Custom pricing available for 1000+ credits'
        }
    })

@app.route('/api/user/<email>/credits', methods=['GET'])
def get_user_credits(email):
    """Get user's credit balance and transaction history"""
    try:
        # Import here to avoid circular imports
        from models import User, CreditTransaction
        
        user = User.query.filter_by(email=email).first()
        if not user:
            # Create new user with free tier credits
            user = User(
                email=email, 
                name=email.split('@')[0].title(),
                credits_balance=25  # Free tier
            )
            db.session.add(user)
            db.session.commit()
        
        # Get recent transactions
        recent_transactions = CreditTransaction.query.filter_by(
            user_id=user.id
        ).order_by(CreditTransaction.created_at.desc()).limit(10).all()
        
        return jsonify({
            'user': {
                'email': user.email,
                'name': user.name,
                'credits_balance': user.credits_balance,
                'total_purchased': user.total_credits_purchased,
                'created_at': user.created_at.isoformat()
            },
            'transactions': [{
                'id': str(t.id),
                'type': t.transaction_type,
                'amount': t.credits_amount,
                'description': t.description,
                'status': t.status,
                'payment_reference': t.payment_reference,
                'amount_usd': t.amount_usd,
                'created_at': t.created_at.isoformat()
            } for t in recent_transactions]
        })
        
    except Exception as e:
        logger.error(f"Error getting user credits: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/purchase-credits', methods=['POST'])
def purchase_credits():
    """Initiate credit purchase via Korapay"""
    try:
        data = request.get_json()
        package_id = data.get('package_id')
        customer_email = data.get('email')
        
        if not package_id or not customer_email:
            return jsonify({'error': 'Package ID and email are required'}), 400
        
        if package_id not in CREDIT_PACKAGES:
            return jsonify({'error': 'Invalid package ID'}), 400
        
        package = CREDIT_PACKAGES[package_id]
        
        # Initialize Korapay service
        korapay = KorapayService()
        
        # Create checkout session
        checkout = korapay.create_checkout_session(
            amount_usd=package['price_usd'],
            customer_email=customer_email,
            credits=package['credits']
        )
        
        if checkout['success']:
            # Import models here to avoid circular imports
            from models import User, CreditTransaction
            
            # Get or create user
            user = User.query.filter_by(email=customer_email).first()
            if not user:
                user = User(
                    email=customer_email, 
                    name=customer_email.split('@')[0].title()
                )
                db.session.add(user)
                db.session.flush()
            
            # Create pending transaction record
            transaction = CreditTransaction(
                user_id=user.id,
                transaction_type='purchase',
                credits_amount=package['credits'],
                payment_reference=checkout['reference'],
                amount_usd=package['price_usd'],
                description=f"Purchase of {package['name']} ({package['credits']} credits)",
                status='pending'
            )
            db.session.add(transaction)
            db.session.commit()
            
            logger.info(f"Created pending transaction {checkout['reference']} for {customer_email}")
            
            return jsonify({
                'success': True,
                'checkout_url': checkout['checkout_url'],
                'reference': checkout['reference'],
                'package': {
                    **package,
                    'id': package_id
                },
                'amount_ngn': checkout['amount_ngn'],
                'instructions': 'You will be redirected to Korapay to complete your payment'
            })
        else:
            return jsonify(checkout), 400
            
    except Exception as e:
        logger.error(f"Payment initiation failed: {str(e)}")
        return jsonify({'error': f'Payment initiation failed: {str(e)}'}), 500

@app.route('/api/webhooks/korapay', methods=['POST'])
def korapay_webhook():
    """Handle Korapay payment webhooks"""
    try:
        # Get signature from headers
        signature = request.headers.get('X-Korapay-Signature', '')
        payload = request.get_data(as_text=True)
        
        korapay = KorapayService()
        
        # Verify webhook signature
        if not korapay.verify_webhook(payload, signature):
            logger.warning("Invalid webhook signature received")
            return jsonify({'error': 'Invalid signature'}), 400
        
        data = request.get_json()
        event_type = data.get('event', '')
        
        logger.info(f"Received Korapay webhook: {event_type}")
        
        if event_type == 'charge.success':
            reference = data['data']['reference']
            amount = data['data']['amount']
            
            # Import models here
            from models import User, CreditTransaction
            
            # Find pending transaction
            transaction = CreditTransaction.query.filter_by(
                payment_reference=reference,
                status='pending'
            ).first()
            
            if transaction:
                # Update transaction status
                transaction.status = 'completed'
                
                # Add credits to user account
                transaction.user.credits_balance += transaction.credits_amount
                transaction.user.total_credits_purchased += transaction.credits_amount
                
                db.session.commit()
                
                logger.info(f"✅ Payment successful: Added {transaction.credits_amount} credits to {transaction.user.email}")
                
                # You could send an email notification here
                
                return jsonify({
                    'status': 'success',
                    'message': 'Credits added successfully'
                })
            else:
                logger.warning(f"Transaction not found for reference: {reference}")
                return jsonify({'error': 'Transaction not found'}), 404
                
        elif event_type == 'charge.failed':
            reference = data['data']['reference']
            
            # Import models here
            from models import CreditTransaction
            
            # Update transaction status
            transaction = CreditTransaction.query.filter_by(
                payment_reference=reference,
                status='pending'
            ).first()
            
            if transaction:
                transaction.status = 'failed'
                db.session.commit()
                
                logger.info(f"❌ Payment failed for reference: {reference}")
        
        return jsonify({'status': 'received'})
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 500

@app.route('/api/verify-payment/<reference>', methods=['GET'])
def verify_payment(reference):
    """Manually verify a payment status"""
    try:
        korapay = KorapayService()
        result = korapay.verify_payment(reference)
        
        if result['success']:
            # Import models here
            from models import CreditTransaction
            
            # Check our database
            transaction = CreditTransaction.query.filter_by(
                payment_reference=reference
            ).first()
            
            if transaction:
                return jsonify({
                    'korapay_status': result['status'],
                    'database_status': transaction.status,
                    'credits': transaction.credits_amount,
                    'amount_usd': transaction.amount_usd,
                    'customer': transaction.user.email,
                    'created_at': transaction.created_at.isoformat()
                })
            else:
                return jsonify({
                    'error': 'Transaction not found in database',
                    'korapay_status': result['status']
                }), 404
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/deduct-credits', methods=['POST'])
def deduct_credits():
    """Deduct credits for API usage (internal endpoint)"""
    try:
        data = request.get_json()
        user_email = data.get('email')
        credits_to_deduct = data.get('credits', 1)
        operation = data.get('operation', 'api_usage')
        
        if not user_email:
            return jsonify({'error': 'Email required'}), 400
        
        # Import models here
        from models import User, CreditTransaction
        
        user = User.query.filter_by(email=user_email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.credits_balance < credits_to_deduct:
            return jsonify({
                'error': 'Insufficient credits',
                'current_balance': user.credits_balance,
                'required': credits_to_deduct
            }), 402  # Payment Required
        
        # Deduct credits
        user.credits_balance -= credits_to_deduct
        
        # Record transaction
        transaction = CreditTransaction(
            user_id=user.id,
            transaction_type='usage',
            credits_amount=-credits_to_deduct,  # Negative for usage
            description=f"Credits used for {operation}",
            status='completed'
        )
        db.session.add(transaction)
        db.session.commit()
        
        logger.info(f"Deducted {credits_to_deduct} credits from {user_email} for {operation}")
        
        return jsonify({
            'success': True,
            'credits_deducted': credits_to_deduct,
            'remaining_balance': user.credits_balance,
            'operation': operation
        })
        
    except Exception as e:
        logger.error(f"Credit deduction error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(401)
def unauthorized(error):
    return jsonify({'error': 'Authentication required'}), 401

@app.errorhandler(403)
def forbidden(error):
    return jsonify({'error': 'Access forbidden'}), 403

@app.errorhandler(429)
def ratelimit_handler(error):
    return jsonify({'error': 'Rate limit exceeded', 'retry_after': 60}), 429

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Create default admin user if it doesn't exist
        admin_email = os.getenv('ADMIN_EMAIL')
        if admin_email:
            admin_user = User.query.filter_by(email=admin_email).first()
            if not admin_user:
                admin_user = User(
                    email=admin_email,
                    first_name='Gabriel',
                    last_name='Effangha',
                    auth_method='email',
                    is_admin=True,
                    is_active=True,
                    email_verified=True,
                    credits_balance=10000  # Give admin lots of credits
                )
                admin_user.set_password(os.getenv('ADMIN_PASSWORD'))
                db.session.add(admin_user)
                db.session.commit()
                logger.info(f"Created admin user: {admin_email}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)