"""
MongoDB Connection Layer

Provides a singleton MongoDB client shared across the entire application.
All blueprints and services use this single connection for efficiency.
"""

from pymongo import MongoClient
from flask import current_app, g


# Global MongoDB client (initialized once)
_mongo_client = None


def init_db(app):
    """
    Initialize MongoDB connection.
    
    Called once during app startup in the app factory.
    Creates a singleton MongoClient instance.
    
    Args:
        app: Flask application instance
    """
    global _mongo_client
    
    if _mongo_client is None:
        mongo_uri = app.config['MONGODB_URI']
        _mongo_client = MongoClient(mongo_uri)
        
        # Test connection
        try:
            _mongo_client.admin.command('ping')
            app.logger.info(f"✓ MongoDB connected: {mongo_uri}")
        except Exception as e:
            app.logger.error(f"✗ MongoDB connection failed: {e}")
            raise


def get_db():
    """
    Get MongoDB database instance.
    
    This function should be called by all blueprints and services
    to access the database. It uses Flask's application context
    to ensure thread safety.
    
    Returns:
        MongoDB database instance
    
    Usage:
        db = get_db()
        mothers_collection = db.mothers
        mothers = mothers_collection.find({})
    """
    if 'db' not in g:
        db_name = current_app.config['MONGODB_DB_NAME']
        g.db = _mongo_client[db_name]
    
    return g.db


def get_collection(collection_name):
    """
    Convenience function to get a specific collection.
    
    Args:
        collection_name: Name of the MongoDB collection
    
    Returns:
        MongoDB collection instance
    
    Usage:
        mothers = get_collection('mothers')
        result = mothers.find_one({'_id': mother_id})
    """
    db = get_db()
    return db[collection_name]
