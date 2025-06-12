from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Text, DateTime, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

# Don't create db instance here. It will be created by app.py and imported.
db = None

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