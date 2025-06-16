-- Migration script to add authentication tables and update existing tables

-- Update existing users table with authentication fields
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(200);
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_method VARCHAR(20) DEFAULT 'email';
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS agreed_to_terms BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS age_confirmed BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token_expires TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_plan VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_free_credit_reset DATE DEFAULT CURRENT_DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS refresh_token VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS refresh_token_expires TIMESTAMP;

-- Add unique constraints and indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_auth_method ON users(auth_method);
CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity);

-- User sessions table for tracking user sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(500) NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    device_info VARCHAR(200),
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

-- API usage logs table for rate limiting and analytics
CREATE TABLE IF NOT EXISTS api_usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint VARCHAR(100) NOT NULL,
    method VARCHAR(10) NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    request_data TEXT,
    response_status INTEGER,
    response_time FLOAT,
    credits_used INTEGER DEFAULT 0,
    rate_limit_key VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_usage_logs_user_id ON api_usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_logs_endpoint ON api_usage_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_api_usage_logs_created_at ON api_usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_logs_rate_limit_key ON api_usage_logs(rate_limit_key);

-- Update existing credit_transactions table to match new model
ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS api_endpoint VARCHAR(100);
ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS batch_size INTEGER;

-- Add trigger to update updated_at column for users
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $BODY$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$BODY$ language 'plpgsql';

-- Create trigger if it doesn't exist
DO $BODY$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_users_updated_at') THEN
        CREATE TRIGGER update_users_updated_at 
        BEFORE UPDATE ON users 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END
$BODY$;

-- Insert some sample data for testing (optional)
-- Update existing users to have proper authentication fields
UPDATE users 
SET 
    email_verified = TRUE,
    is_active = TRUE,
    current_plan = 'free',
    auth_method = 'email'
WHERE auth_method IS NULL;

-- Create admin user if ADMIN_EMAIL environment variable is set
-- This will be handled by the application code instead

-- Add some indexes for better performance
CREATE INDEX IF NOT EXISTS idx_credit_transactions_api_endpoint ON credit_transactions(api_endpoint);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_batch_size ON credit_transactions(batch_size);

-- Add check constraints for data integrity
ALTER TABLE users ADD CONSTRAINT chk_auth_method 
    CHECK (auth_method IN ('email', 'google'));

ALTER TABLE users ADD CONSTRAINT chk_current_plan 
    CHECK (current_plan IN ('free', 'starter', 'professional', 'business', 'enterprise'));

ALTER TABLE credit_transactions ADD CONSTRAINT chk_transaction_type 
    CHECK (transaction_type IN ('purchase', 'usage', 'refund', 'free_reset'));

ALTER TABLE credit_transactions ADD CONSTRAINT chk_status 
    CHECK (status IN ('pending', 'completed', 'failed', 'refunded'));

-- Update any existing users to have valid plans
UPDATE users SET current_plan = 'free' WHERE current_plan IS NULL OR current_plan = '';

-- Ensure all users have credits_balance set
UPDATE users SET credits_balance = 25 WHERE credits_balance IS NULL;

-- Set display_name for users who don't have it
UPDATE users SET display_name = CONCAT(first_name, ' ', last_name) 
WHERE display_name IS NULL AND first_name IS NOT NULL AND last_name IS NOT NULL;

UPDATE users SET display_name = SPLIT_PART(email, '@', 1) 
WHERE display_name IS NULL;

COMMIT;