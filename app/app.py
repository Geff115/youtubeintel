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

# Import models after database is initialized
from models import Channel, Video, APIKey, ProcessingJob, ChannelDiscovery

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

if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
    
    app.run(host='0.0.0.0', port=5000, debug=True)