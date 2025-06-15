"""
Database configuration module - Updated for Supabase
Separates database setup from Flask app to avoid circular imports
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

# Create SQLAlchemy instance
db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """Initialize database with Flask app"""
    
    # Always use the DATABASE_URL from environment (Supabase)
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Optimize for production with Supabase
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 20,
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'connect_args': {
            'connect_timeout': 10,
            'application_name': 'YouTubeIntel'
        }
    }
    
    db.init_app(app)
    migrate.init_app(app, db)
    
    print(f"✅ Database initialized: {database_url.split('@')[1].split('/')[0] if '@' in database_url else 'Unknown'}")
    
    return db