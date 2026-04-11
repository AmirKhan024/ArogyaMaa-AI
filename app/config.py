"""
Configuration Management

Loads environment variables from .env file and provides configuration classes.
Uses python-dotenv to read .env file.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Base configuration class.
    
    All configuration values are loaded from environment variables.
    This ensures sensitive data (API keys, tokens) are never hardcoded.
    """
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # MongoDB settings
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'ArogyaMaa')
    
    # Telegram Bot settings
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    # Groq API settings (for AI inference)
    GROQ_API_KEY = os.getenv('GROQ_API_KEY')
    LLM_MODEL = os.getenv('LLM_MODEL', 'llama-3.1-70b-versatile')
    
    # LangSmith settings (for AI observability)
    LANGSMITH_API_KEY = os.getenv('LANGSMITH_API_KEY')
    LANGSMITH_PROJECT = os.getenv('LANGSMITH_PROJECT', 'ArogyaMaa')
    LANGCHAIN_TRACING_V2 = os.getenv('LANGCHAIN_TRACING_V2', 'true')
    
    # Server settings
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))
    
    # Feature flags
    DEV_MODE = os.getenv('DEV_MODE', 'False').lower() == 'true'
    ENABLE_AI_ADVISORY = os.getenv('ENABLE_AI_ADVISORY', 'True').lower() == 'true'


class DevelopmentConfig(Config):
    """Development-specific configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production-specific configuration"""
    DEBUG = False


# Configuration dictionary
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig
}


def get_config(config_name='development'):
    """
    Get configuration class by name.
    
    Args:
        config_name: 'development' or 'production'
    
    Returns:
        Configuration class
    """
    return config_by_name.get(config_name, DevelopmentConfig)
