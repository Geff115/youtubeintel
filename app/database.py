"""
Database configuration module
Separates database setup from Flask app to avoid circular imports
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Create SQLAlchemy instance
db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """Initialize database with Flask app"""
    db.init_app(app)
    migrate.init_app(app, db)
    return db