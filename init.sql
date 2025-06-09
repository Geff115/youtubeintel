-- Database initialization script
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Channels table
CREATE TABLE channels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel_id VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    subscriber_count BIGINT,
    video_count BIGINT,
    view_count BIGINT,
    country VARCHAR(10),
    language VARCHAR(10),
    custom_url VARCHAR(255),
    published_at TIMESTAMP,
    thumbnail_url VARCHAR(500),
    banner_url VARCHAR(500),
    keywords TEXT[],
    topic_categories TEXT[],
    
    -- Processing status
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata_fetched BOOLEAN DEFAULT FALSE,
    videos_fetched BOOLEAN DEFAULT FALSE,
    discovery_processed BOOLEAN DEFAULT FALSE,
    
    -- Source tracking
    source VARCHAR(50) DEFAULT 'migration', -- migration, discovery, manual
    discovered_from UUID REFERENCES channels(id),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Videos table
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id VARCHAR(255) UNIQUE NOT NULL,
    channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    channel_external_id VARCHAR(255) NOT NULL,
    title VARCHAR(500),
    description TEXT,
    published_at TIMESTAMP,
    duration VARCHAR(20),
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT,
    thumbnail_url VARCHAR(500),
    tags TEXT[],
    category_id INTEGER,
    language VARCHAR(10),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API Keys management
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key_name VARCHAR(100) NOT NULL,
    api_key VARCHAR(255) NOT NULL,
    service VARCHAR(50) NOT NULL DEFAULT 'youtube', -- youtube, external_service_1, etc.
    quota_limit INTEGER DEFAULT 10000,
    quota_used INTEGER DEFAULT 0,
    quota_reset_date DATE DEFAULT CURRENT_DATE,
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processing jobs tracking
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type VARCHAR(50) NOT NULL, -- 'metadata_fetch', 'video_fetch', 'discovery'
    status VARCHAR(20) DEFAULT 'pending', -- pending, running, completed, failed
    channel_id UUID REFERENCES channels(id),
    total_items INTEGER,
    processed_items INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- External service discoveries
CREATE TABLE channel_discoveries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_channel_id UUID NOT NULL REFERENCES channels(id),
    discovered_channel_id VARCHAR(255) NOT NULL,
    discovery_method VARCHAR(50) NOT NULL, -- 'related_channels', 'similar_content', etc.
    service_name VARCHAR(50) NOT NULL,
    confidence_score FLOAT,
    already_exists BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(source_channel_id, discovered_channel_id, discovery_method)
);

-- Create indexes
CREATE INDEX idx_channels_channel_id ON channels(channel_id);
CREATE INDEX idx_channels_last_updated ON channels(last_updated);
CREATE INDEX idx_channels_metadata_fetched ON channels(metadata_fetched);
CREATE INDEX idx_channels_videos_fetched ON channels(videos_fetched);
CREATE INDEX idx_channels_discovery_processed ON channels(discovery_processed);

CREATE INDEX idx_videos_channel_id ON videos(channel_id);
CREATE INDEX idx_videos_video_id ON videos(video_id);
CREATE INDEX idx_videos_published_at ON videos(published_at);

CREATE INDEX idx_api_keys_service ON api_keys(service);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);

CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX idx_processing_jobs_job_type ON processing_jobs(job_type);

CREATE INDEX idx_channel_discoveries_source ON channel_discoveries(source_channel_id);
CREATE INDEX idx_channel_discoveries_discovered ON channel_discoveries(discovered_channel_id);

-- Create trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_channels_updated_at BEFORE UPDATE ON channels FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_videos_updated_at BEFORE UPDATE ON videos FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_api_keys_updated_at BEFORE UPDATE ON api_keys FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();