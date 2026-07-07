"""
Configuration Management

Loads environment variables from .env file and provides configuration classes.
Uses python-dotenv to read .env file.

External services: Supabase Postgres (DATABASE_URL) + Groq (GROQ_API_KEY) only.
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
    SECRET_KEY = os.getenv('SECRET_KEY')  # REQUIRED — no fallback (see app/__init__.py)
    APP_ENV = os.getenv('APP_ENV', 'development')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    # Database (Supabase / Postgres) — SQLAlchemy + psycopg
    DATABASE_URL = os.getenv('DATABASE_URL')

    # Telegram Bot settings
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    APPOINTMENT_WEBHOOK_PORT = int(os.getenv('APPOINTMENT_WEBHOOK_PORT', 5050))

    # Internal service auth (bot -> guarded API routes)
    INTERNAL_API_TOKEN = os.getenv('INTERNAL_API_TOKEN')

    # Development-only static admin login (no admins table in this prototype).
    # Leave ADMIN_PASSWORD unset to disable. Never used when APP_ENV != development.
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

    # Groq AI settings (LLM + Whisper STT) — the only AI key needed
    GROQ_API_KEY = os.getenv('GROQ_API_KEY')
    LLM_MODEL = os.getenv('LLM_MODEL', 'openai/gpt-oss-120b')
    LLM_MODEL_FAST = os.getenv('LLM_MODEL_FAST', 'llama-3.1-8b-instant')
    WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'whisper-large-v3')

    # LangSmith settings (for AI observability)
    LANGSMITH_API_KEY = os.getenv('LANGSMITH_API_KEY')
    LANGSMITH_PROJECT = os.getenv('LANGSMITH_PROJECT', 'ArogyaMaa')
    LANGCHAIN_TRACING_V2 = os.getenv('LANGCHAIN_TRACING_V2', 'false')

    # Server settings
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))

    # Feature flags
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
