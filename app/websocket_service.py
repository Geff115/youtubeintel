import logging
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from flask import request
from auth import auth_service
from models import User, ProcessingJob, CreditTransaction
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Initialize SocketIO
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=False,
    ping_interval=10,
    ping_timeout=30,
    transports=['websocket']
)

# Store active connections
active_connections = {}

def authenticate_socket(auth_token):
    """Authenticate WebSocket connection using JWT token"""
    # Create a scoped session for this connection
    from database import db
    session = db.create_scoped_session()

    try:
        logger.info(f"Attempting to authenticate with token: {auth_token[:20]}...")  # Log first 20 chars

        if not auth_token:
            logger.warning("No auth token provided for WebSocket connection")
            return None
        
        # Remove 'Bearer ' prefix if present
        if auth_token.startswith('Bearer '):
            auth_token = auth_token[7:]
            logger.info("Removed Bearer prefix from token")
        
        # Verify token
        payload = auth_service.verify_jwt_token(auth_token)
        logger.info(f"Token payload: {payload}")

        if not payload:
            logger.warning("Invalid JWT token for WebSocket")
            return None
            
        user = session.query(User).get(payload['user_id'])
        
        if user and user.is_active:
            logger.info(f"WebSocket authentication successful for user: {user.email}")
            return user
        else:
            logger.warning(f"User not found or inactive: {payload.get('user_id')}")
            return None
            
    except Exception as e:
        logger.error(f"Socket authentication failed: {str(e)}")
        return None
    
    finally:
        session.remove()

@socketio.on('connect')
def handle_connect(auth):
    """Handle client connection"""
    try:
        logger.info(f"WebSocket connection attempt from {request.sid}")
        
        # Get token from multiple sources
        auth_token = None
        
        # Try auth object first
        if auth and isinstance(auth, dict):
            auth_token = auth.get('token')
        
        # Try query parameters
        if not auth_token:
            auth_token = request.args.get('token')
        
        # Try headers
        if not auth_token:
            auth_header = request.headers.get('Authorization')
            if auth_header:
                auth_token = auth_header.replace('Bearer ', '')
        
        if not auth_token:
            logger.error("No token provided in any expected location")
            disconnect()
            return False
        
        # Authenticate user
        user = authenticate_socket(auth_token)
        
        if user:
            # Join user to their personal room
            user_room = f"user_{str(user.id)}"  # Convert UUID to string
            join_room(user_room)
            
            # Store connection
            active_connections[request.sid] = {
                'user_id': str(user.id),
                'email': user.email,
                'connected_at': datetime.utcnow()
            }
            
            # Send connection confirmation
            emit('connection_status', {
                'status': 'connected',
                'user_id': str(user.id),
                'timestamp': datetime.utcnow().isoformat()
            })
            
            logger.info(f"User {user.email} connected successfully")
            return True
        else:
            logger.error("Authentication failed")
            disconnect()
            return False
            
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        disconnect()
        return False

@socketio.on('authenticate')
def handle_authenticate(data):
    """Handle authentication requests during the session"""
    try:
        if request.sid not in active_connections:
            logger.warning(f"Authentication request from unconnected session: {request.sid}")
            emit('auth_error', {'message': 'Not connected'})
            return
            
        user_info = active_connections[request.sid]
        emit('auth_success', {
            'user_id': user_info['user_id'],
            'email': user_info['email']
        })
        
    except Exception as e:
        logger.error(f"Authentication handler error: {str(e)}")
        emit('auth_error', {'message': 'Authentication failed'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    try:
        if request.sid in active_connections:
            user_info = active_connections[request.sid]
            user_id = user_info['user_id']
            
            # Leave user room
            leave_room(f"user_{str(user_id)}")
            
            # Remove from active connections
            del active_connections[request.sid]
            
            logger.info(f"User {user_info['email']} disconnected: {request.sid}")
    except Exception as e:
        logger.error(f"Disconnect error: {str(e)}")

@socketio.on('subscribe_to_job')
def handle_job_subscription(data):
    """Subscribe to specific job updates"""
    try:
        job_id = data.get('job_id')
        if not job_id:
            emit('error', {'message': 'Job ID required'})
            return
        
        # Verify user has access to this job
        user_info = active_connections.get(request.sid)
        if not user_info:
            emit('error', {'message': 'Not authenticated'})
            return
        
        # Join job-specific room
        join_room(f"job_{str(job_id)}")
        
        # Send current job status
        job = ProcessingJob.query.filter_by(job_id=job_id).first()
        if job:
            emit('job_update', {
                'job_id': str(job_id),
                'status': job.status,
                'progress': job.progress or 0,
                'message': f"Subscribed to job {job_id}",
                'timestamp': datetime.utcnow().isoformat()
            })
        
        logger.info(f"User {user_info['email']} subscribed to job {job_id}")
        
    except Exception as e:
        logger.error(f"Job subscription error: {str(e)}")
        emit('error', {'message': 'Subscription failed'})

def send_pending_notifications(user_id):
    """Send any pending notifications to newly connected user"""
    try:
        # Get recent completed jobs
        recent_jobs = ProcessingJob.query.filter_by(
            status='completed'
        ).order_by(ProcessingJob.completed_at.desc()).limit(5).all()
        
        for job in recent_jobs:
            socketio.emit('job_completed', {
                'job_id': job.job_id,
                'job_type': job.job_type,
                'total_items': job.total_items,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'message': f'{job.job_type} completed successfully'
            }, room=f"user_{str(user_id)}")
        
        # Get recent credit transactions
        recent_transactions = CreditTransaction.query.filter_by(
            user_id=user_id
        ).order_by(CreditTransaction.created_at.desc()).limit(3).all()
        
        for transaction in recent_transactions:
            if transaction.transaction_type == 'purchase' and transaction.status == 'completed':
                socketio.emit('credits_updated', {
                    'type': 'purchase',
                    'amount': transaction.credits_amount,
                    'new_balance': transaction.user.credits_balance,
                    'message': f'Credits purchased: +{transaction.credits_amount}',
                    'timestamp': transaction.created_at.isoformat()
                }, room=f"user_{str(user_id)}")
                
    except Exception as e:
        logger.error(f"Error sending pending notifications: {str(e)}")

# Real-time update functions to call from our existing code

def notify_job_progress(job_id, status, progress=None, message=None, error=None):
    """Notify clients about job progress"""
    try:
        socketio.emit('job_update', {
            'job_id': str(job_id),
            'status': status,
            'progress': progress,
            'message': message,
            'error': error,
            'timestamp': datetime.utcnow().isoformat()
        }, room=f"job_{str(job_id)}")
        
        logger.info(f"Sent job update for {job_id}: {status}")
    except Exception as e:
        logger.error(f"Error sending job update: {str(e)}")

def notify_job_completed(job_id, job_type, total_items=None, user_id=None):
    """Notify when job is completed"""
    try:
        notification = {
            'job_id': str(job_id),
            'job_type': job_type,
            'total_items': total_items,
            'message': f'{job_type.replace("_", " ").title()} completed successfully',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Send to job subscribers
        socketio.emit('job_completed', notification, room=f"job_{jstr(job_id)}")
        
        # Send to user if specified
        if user_id:
            socketio.emit('job_completed', notification, room=f"user_{str(user_id)}")
            
        logger.info(f"Sent job completion notification for {job_id}")
    except Exception as e:
        logger.error(f"Error sending job completion: {str(e)}")

def notify_credits_updated(user_id, transaction_type, amount, new_balance, message=None):
    """Notify about credit balance changes"""
    try:
        socketio.emit('credits_updated', {
            'type': transaction_type,
            'amount': amount,
            'new_balance': new_balance,
            'message': message or f'Credits {transaction_type}: {amount:+d}',
            'timestamp': datetime.utcnow().isoformat()
        }, room=f"user_{str(user_id)}")
        
        logger.info(f"Sent credit update to user {user_id}: {amount:+d}")
    except Exception as e:
        logger.error(f"Error sending credit update: {str(e)}")

def notify_discovery_results(user_id, channel_count, discovery_method, job_id=None):
    """Notify about new discovery results"""
    try:
        socketio.emit('discovery_results', {
            'channel_count': channel_count,
            'discovery_method': discovery_method,
            'job_id': str(job_id) if job_id else None,
            'message': f'Found {channel_count} new channels via {discovery_method}',
            'timestamp': datetime.utcnow().isoformat()
        }, room=f"user_{str(user_id)}")
        
        logger.info(f"Sent discovery results to user {user_id}: {channel_count} channels")
    except Exception as e:
        logger.error(f"Error sending discovery results: {str(e)}")

def get_active_connections_count():
    """Get count of active WebSocket connections"""
    return len(active_connections)

def get_user_connection_status(user_id):
    """Check if user has active WebSocket connection"""
    user_id_str = str(user_id)  # Convert to string for comparison
    for sid, info in active_connections.items():
        if info['user_id'] == user_id_str:
            return True
    return False