from app.database import db
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Text, DateTime, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255))  # For traditional signup
    
    # Profile information
    first_name = Column(String(100))
    last_name = Column(String(100))
    display_name = Column(String(200))  # Computed from first + last or Google name
    profile_picture = Column(String(500))  # URL to profile image
    
    # Authentication methods
    auth_method = Column(String(20), default='email')  # 'email' or 'google'
    google_id = Column(String(100), unique=True, index=True)  # Google OAuth ID
    email_verified = Column(Boolean, default=False)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    agreed_to_terms = Column(Boolean, default=False)
    age_confirmed = Column(Boolean, default=False)  # 18+ confirmation
    
    # Password reset
    reset_token = Column(String(100))
    reset_token_expires = Column(DateTime)
    
    # Email verification
    verification_token = Column(String(100))
    verification_token_expires = Column(DateTime)
    
    # Credits and billing
    credits_balance = Column(Integer, default=25)  # Free tier: 25 credits
    total_credits_purchased = Column(Integer, default=0)
    current_plan = Column(String(50), default='free')  # free, starter, professional, business, enterprise
    last_free_credit_reset = Column(Date, default=datetime.utcnow().date())
    
    # Session management
    last_login = Column(DateTime)
    last_activity = Column(DateTime)
    refresh_token = Column(String(500))  # For JWT refresh
    refresh_token_expires = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    credit_transactions = relationship("CreditTransaction", back_populates="user", cascade="all, delete-orphan")
    api_usage_logs = relationship("APIUsageLog", back_populates="user", cascade="all, delete-orphan")
    user_sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<User {self.email}: {self.credits_balance} credits>'
    
    @property
    def full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.display_name:
            return self.display_name
        else:
            return self.email.split('@')[0].title()
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': self.full_name,
            'display_name': self.display_name,
            'profile_picture': self.profile_picture,
            'auth_method': self.auth_method,
            'email_verified': self.email_verified,
            'is_active': self.is_active,
            'credits_balance': self.credits_balance,
            'total_credits_purchased': self.total_credits_purchased,
            'current_plan': self.current_plan,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
    
    def can_afford(self, credits_needed: int) -> bool:
        """Check if user has enough credits"""
        return self.credits_balance >= credits_needed
    
    def deduct_credits(self, amount: int, description: str = "API usage", endpoint: str = None):
        """Deduct credits and create transaction record"""
        if not self.can_afford(amount):
            raise ValueError(f"Insufficient credits. Need {amount}, have {self.credits_balance}")
        
        self.credits_balance -= amount
        self.last_activity = datetime.utcnow()
        
        # Create usage transaction
        transaction = CreditTransaction(
            user_id=self.id,
            transaction_type='usage',
            credits_amount=-amount,
            description=description,
            status='completed',
            api_endpoint=endpoint
        )
        db.session.add(transaction)
        return transaction
    
    def add_credits(self, amount: int, payment_reference: str = None, amount_usd: float = None, description: str = "Credits purchased"):
        """Add credits and create transaction record"""
        self.credits_balance += amount
        self.total_credits_purchased += amount
        
        # Create purchase transaction
        transaction = CreditTransaction(
            user_id=self.id,
            transaction_type='purchase',
            credits_amount=amount,
            payment_reference=payment_reference,
            amount_usd=amount_usd,
            description=description,
            status='completed'
        )
        db.session.add(transaction)
        return transaction
    
    def reset_free_credits(self):
        """Reset free tier credits monthly"""
        from datetime import date
        today = date.today()
        
        if self.last_free_credit_reset < today:
            if self.current_plan == 'free':
                self.credits_balance = max(self.credits_balance, 25)  # Ensure at least 25 credits
                self.last_free_credit_reset = today
                
                # Create reset transaction
                transaction = CreditTransaction(
                    user_id=self.id,
                    transaction_type='free_reset',
                    credits_amount=25,
                    description="Monthly free credits reset",
                    status='completed'
                )
                db.session.add(transaction)
                return transaction
        return None
    
    def set_password(self, password: str):
        """Set user password (hashed)"""
        from app.auth import auth_service
        self.password_hash = auth_service.hash_password(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify user password"""
        if not self.password_hash:
            return False
        from app.auth import auth_service
        return auth_service.verify_password(password, self.password_hash)
    
    def generate_reset_token(self):
        """Generate password reset token"""
        from app.auth import auth_service
        from datetime import timedelta, datetime
        self.reset_token = auth_service.generate_reset_token()
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
        return self.reset_token
    
    def generate_verification_token(self):
        """Generate email verification token"""
        from app.auth import auth_service
        from datetime import timedelta, datetime
        self.verification_token = auth_service.generate_reset_token()
        self.verification_token_expires = datetime.utcnow() + timedelta(hours=24)  # 24 hour expiry
        return self.verification_token
    
    def verify_email(self):
        """Mark email as verified and clear verification token"""
        self.email_verified = True
        self.verification_token = None
        self.verification_token_expires = None
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
    
    def create_session(self, refresh_token: str):
        """Create new user session"""
        from datetime import timedelta, datetime
        self.refresh_token = refresh_token
        self.refresh_token_expires = datetime.utcnow() + timedelta(days=30)
        self.last_login = datetime.utcnow()
        self.update_activity()
    
    def clear_session(self):
        """Clear user session"""
        self.refresh_token = None
        self.refresh_token_expires = None
    
    def is_session_valid(self) -> bool:
        """Check if current session is valid"""
        from datetime import datetime
        if not self.refresh_token or not self.refresh_token_expires:
            return False
        return datetime.utcnow() < self.refresh_token_expires

class UserSession(db.Model):
    """Track user sessions for security"""
    __tablename__ = 'user_sessions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    session_token = Column(String(500), nullable=False, index=True)
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(String(500))
    device_info = Column(String(200))
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="user_sessions")
    
    def __repr__(self):
        return f'<UserSession {self.user.email}: {self.device_info}>'
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'ip_address': self.ip_address,
            'device_info': self.device_info,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }
    
    def update_activity(self):
        """Update session activity"""
        from datetime import datetime
        self.last_activity = datetime.utcnow()
    
    def is_expired(self) -> bool:
        """Check if session is expired"""
        from datetime import datetime
        return datetime.utcnow() > self.expires_at
    
    def deactivate(self):
        """Deactivate session"""
        self.is_active = False

class APIUsageLog(db.Model):
    """Track API usage for rate limiting and analytics"""
    __tablename__ = 'api_usage_logs'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    endpoint = Column(String(100), nullable=False)
    method = Column(String(10), nullable=False)  # GET, POST, etc.
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    
    # Request details
    request_data = Column(Text)  # JSON string of request data
    response_status = Column(Integer)
    response_time = Column(Float)  # in milliseconds
    credits_used = Column(Integer, default=0)
    
    # Rate limiting
    rate_limit_key = Column(String(100))  # For grouping requests
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="api_usage_logs")
    
    def __repr__(self):
        return f'<APIUsageLog {self.user.email}: {self.endpoint}>'
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'endpoint': self.endpoint,
            'method': self.method,
            'response_status': self.response_status,
            'response_time': self.response_time,
            'credits_used': self.credits_used,
            'created_at': self.created_at.isoformat()
        }

class Channel(db.Model):
    __tablename__ = 'channels'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(500))
    description = Column(Text)
    subscriber_count = Column(BigInteger)
    video_count = Column(BigInteger)
    view_count = Column(BigInteger)
    country = Column(String(10))
    language = Column(String(10))
    custom_url = Column(String(255))
    published_at = Column(DateTime)
    thumbnail_url = Column(String(500))
    banner_url = Column(String(500))
    keywords = Column(ARRAY(Text))
    topic_categories = Column(ARRAY(Text))
    
    # Processing status
    last_updated = Column(DateTime, default=datetime.utcnow)
    metadata_fetched = Column(Boolean, default=False)
    videos_fetched = Column(Boolean, default=False)
    discovery_processed = Column(Boolean, default=False)
    
    # Source tracking
    source = Column(String(50), default='migration')
    discovered_from = Column(UUID(as_uuid=True), ForeignKey('channels.id'))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")
    discoveries_as_source = relationship("ChannelDiscovery", 
                                       foreign_keys="ChannelDiscovery.source_channel_id",
                                       back_populates="source_channel",
                                       cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Channel {self.channel_id}: {self.title}>'
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'channel_id': self.channel_id,
            'title': self.title,
            'description': self.description,
            'subscriber_count': self.subscriber_count,
            'video_count': self.video_count,
            'view_count': self.view_count,
            'country': self.country,
            'language': self.language,
            'custom_url': self.custom_url,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'thumbnail_url': self.thumbnail_url,
            'banner_url': self.banner_url,
            'keywords': self.keywords,
            'topic_categories': self.topic_categories,
            'metadata_fetched': self.metadata_fetched,
            'videos_fetched': self.videos_fetched,
            'discovery_processed': self.discovery_processed,
            'source': self.source,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class Video(db.Model):
    __tablename__ = 'videos'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id = Column(String(255), unique=True, nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey('channels.id'), nullable=False)
    channel_external_id = Column(String(255), nullable=False)
    title = Column(String(500))
    description = Column(Text)
    published_at = Column(DateTime)
    duration = Column(String(20))
    view_count = Column(BigInteger)
    like_count = Column(BigInteger)
    comment_count = Column(BigInteger)
    thumbnail_url = Column(String(500))
    tags = Column(ARRAY(Text))
    category_id = Column(Integer)
    language = Column(String(10))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    channel = relationship("Channel", back_populates="videos")
    
    def __repr__(self):
        return f'<Video {self.video_id}: {self.title}>'
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'video_id': self.video_id,
            'channel_id': str(self.channel_id),
            'channel_external_id': self.channel_external_id,
            'title': self.title,
            'description': self.description,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'duration': self.duration,
            'view_count': self.view_count,
            'like_count': self.like_count,
            'comment_count': self.comment_count,
            'thumbnail_url': self.thumbnail_url,
            'tags': self.tags,
            'category_id': self.category_id,
            'language': self.language,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class APIKey(db.Model):
    __tablename__ = 'api_keys'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_name = Column(String(100), nullable=False)
    api_key = Column(String(255), nullable=False)
    service = Column(String(50), nullable=False, default='youtube')
    quota_limit = Column(Integer, default=10000)
    quota_used = Column(Integer, default=0)
    quota_reset_date = Column(Date, default=datetime.utcnow().date())
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime)
    error_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<APIKey {self.key_name} ({self.service})>'
    
    def can_use(self):
        """Check if API key can be used (not exceeded quota)"""
        return self.is_active and self.quota_used < self.quota_limit
    
    def increment_usage(self, amount=1):
        """Increment quota usage"""
        self.quota_used += amount
        self.last_used = datetime.utcnow()
    
    def reset_quota(self):
        """Reset daily quota"""
        self.quota_used = 0
        self.quota_reset_date = datetime.utcnow().date()
        self.error_count = 0

class ProcessingJob(db.Model):
    __tablename__ = 'processing_jobs'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type = Column(String(50), nullable=False)
    status = Column(String(20), default='pending')
    channel_id = Column(UUID(as_uuid=True), ForeignKey('channels.id'))
    total_items = Column(Integer)
    processed_items = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProcessingJob {self.job_type}: {self.status}>'
    
    def start(self):
        """Mark job as started"""
        self.status = 'running'
        self.started_at = datetime.utcnow()
    
    def complete(self):
        """Mark job as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
    
    def fail(self, error_message):
        """Mark job as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = datetime.utcnow()
    
    def update_progress(self, processed_items):
        """Update progress"""
        self.processed_items = processed_items

class ChannelDiscovery(db.Model):
    __tablename__ = 'channel_discoveries'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_channel_id = Column(UUID(as_uuid=True), ForeignKey('channels.id'), nullable=False)
    discovered_channel_id = Column(String(255), nullable=False)
    discovery_method = Column(String(50), nullable=False)
    service_name = Column(String(50), nullable=False)
    confidence_score = Column(Float)
    already_exists = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    source_channel = relationship("Channel", 
                                foreign_keys=[source_channel_id],
                                back_populates="discoveries_as_source")
    
    def __repr__(self):
        return f'<ChannelDiscovery {self.discovered_channel_id} via {self.discovery_method}>'
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'source_channel_id': str(self.source_channel_id),
            'discovered_channel_id': self.discovered_channel_id,
            'discovery_method': self.discovery_method,
            'service_name': self.service_name,
            'confidence_score': self.confidence_score,
            'already_exists': self.already_exists,
            'created_at': self.created_at.isoformat()
        }

class CreditTransaction(db.Model):
    __tablename__ = 'credit_transactions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    transaction_type = Column(String(20), nullable=False)  # 'purchase', 'usage', 'refund', 'free_reset'
    credits_amount = Column(Integer, nullable=False)  # Positive for purchase/reset, negative for usage
    payment_reference = Column(String(255))  # Korapay reference for purchases
    amount_usd = Column(Float)  # USD amount for purchases
    description = Column(String(500))
    status = Column(String(20), default='pending')  # 'pending', 'completed', 'failed', 'refunded'
    
    # Metadata for analytics
    api_endpoint = Column(String(100))  # Which API was used (for usage transactions)
    batch_size = Column(Integer)  # For batch operations
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="credit_transactions")
    
    def __repr__(self):
        return f'<CreditTransaction {self.transaction_type}: {self.credits_amount} credits for {self.user.email}>'
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'transaction_type': self.transaction_type,
            'credits_amount': self.credits_amount,
            'payment_reference': self.payment_reference,
            'amount_usd': self.amount_usd,
            'description': self.description,
            'status': self.status,
            'api_endpoint': self.api_endpoint,
            'batch_size': self.batch_size,
            'created_at': self.created_at.isoformat()
        }

# Credit cost configuration
CREDIT_COSTS = {
    'channel_discovery': 1,        # 1 credit per channel discovered
    'channel_metadata': 2,         # 2 credits for full channel analysis  
    'batch_process_100': 5,        # 5 credits for processing 100 channels
    'video_analysis': 1,           # 1 credit per video analyzed
    'export_data': 1,              # 1 credit for data export
}

def calculate_credits_needed(operation: str, quantity: int = 1) -> int:
    """Calculate credits needed for an operation"""
    base_cost = CREDIT_COSTS.get(operation, 1)
    return base_cost * quantity