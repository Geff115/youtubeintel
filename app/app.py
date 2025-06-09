from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from dotenv import load_dotenv
import uuid
from datetime import datetime
from tasks import (
    migrate_channel_data, 
    fetch_channel_metadata, 
    fetch_channel_videos,
    discover_related_channels,
    celery_app
)

load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/youtube_channels')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Import models after db initialization
from models import Channel, Video, APIKey, ProcessingJob, ChannelDiscovery

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

@app.route('/api/migrate', methods=['POST'])
def start_migration():
    """Start channel data migration from existing sources"""
    data = request.get_json() or {}
    source_type = data.get('source_type', 'mysql')  # mysql, csv, json
    source_path = data.get('source_path', '')
    batch_size = data.get('batch_size', 1000)
    
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
        'message': f'Migration started for {source_type} source'
    })

@app.route('/api/fetch-metadata', methods=['POST'])
def start_metadata_fetch():
    """Start fetching metadata for channels"""
    data = request.get_json() or {}
    channel_ids = data.get('channel_ids', [])  # Specific channels, or empty for all
    limit = data.get('limit', 100)  # Max channels to process
    
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

@app.route('/api/fetch-videos', methods=['POST'])
def start_video_fetch():
    """Start fetching videos for channels"""
    data = request.get_json() or {}
    channel_ids = data.get('channel_ids', [])
    videos_per_channel = data.get('videos_per_channel', 50)
    limit = data.get('limit', 100)
    
    # Create processing job
    job = ProcessingJob(
        job_type='video_fetch',
        status='pending',
        total_items=limit
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

@app.route('/api/discover-channels', methods=['POST'])
def start_channel_discovery():
    """Start discovering related channels"""
    data = request.get_json() or {}
    source_channel_ids = data.get('channel_ids', [])
    discovery_methods = data.get('methods', ['related_channels', 'similar_content'])
    limit = data.get('limit', 50)
    
    # Create processing job
    job = ProcessingJob(
        job_type='discovery',
        status='pending',
        total_items=limit
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
        'message': f'Channel discovery started with methods: {discovery_methods}'
    })

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

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List processing jobs with optional filtering"""
    status = request.args.get('status')
    job_type = request.args.get('job_type')
    limit = int(request.args.get('limit', 50))
    
    query = ProcessingJob.query
    if status:
        query = query.filter_by(status=status)
    if job_type:
        query = query.filter_by(job_type=job_type)
    
    jobs = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()
    
    return jsonify([{
        'job_id': str(job.id),
        'job_type': job.job_type,
        'status': job.status,
        'total_items': job.total_items,
        'processed_items': job.processed_items,
        'progress': (job.processed_items / job.total_items * 100) if job.total_items else 0,
        'created_at': job.created_at.isoformat(),
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None
    } for job in jobs])

@app.route('/api/api-keys', methods=['GET'])
def list_api_keys():
    """List API keys (masked for security)"""
    keys = APIKey.query.all()
    return jsonify([{
        'id': str(key.id),
        'key_name': key.key_name,
        'service': key.service,
        'api_key': f"{key.api_key[:8]}...{key.api_key[-4:]}",
        'quota_limit': key.quota_limit,
        'quota_used': key.quota_used,
        'quota_reset_date': key.quota_reset_date.isoformat(),
        'is_active': key.is_active,
        'last_used': key.last_used.isoformat() if key.last_used else None,
        'error_count': key.error_count
    } for key in keys])

@app.route('/api/api-keys', methods=['POST'])
def add_api_key():
    """Add new API key"""
    data = request.get_json()
    required_fields = ['key_name', 'api_key', 'service']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': f'Missing required fields: {required_fields}'}), 400
    
    key = APIKey(
        key_name=data['key_name'],
        api_key=data['api_key'],
        service=data['service'],
        quota_limit=data.get('quota_limit', 10000)
    )
    
    db.session.add(key)
    db.session.commit()
    
    return jsonify({
        'message': 'API key added successfully',
        'key_id': str(key.id)
    }), 201

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    app.run(host='0.0.0.0', port=5000, debug=True)