"""
ArogyaMaa Flask Application Factory

This module implements the Flask app factory pattern.
It creates and configures the Flask application with all necessary blueprints.
"""

from flask import Flask
from app.config import get_config
from app.db import init_db


def create_app(config_name='development'):
    """
    Application factory function.
    
    Creates and configures the Flask application instance with:
    - Configuration from .env
    - MongoDB connection
    - All blueprints (Telegram, Admin, ASHA, Doctor, AI)
    
    Args:
        config_name: Configuration environment ('development' or 'production')
    
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration from config.py (which reads .env)
    config = get_config(config_name)
    app.config.from_object(config)
    
    # Ensure SECRET_KEY is set for sessions
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'ArogyaMaa-dev-secret-key-change-in-prod'
    
    # Initialize MongoDB connection (singleton)
    with app.app_context():
        init_db(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register route protection
    register_route_protection(app)
    
    return app


def register_blueprints(app):
    """
    Register all Flask blueprints with their URL prefixes.
    
    Blueprint structure:
    - /telegram           → Telegram bot webhook
    - /admin              → Admin dashboard APIs
    - /admin/dashboard    → Admin web interface (HTML)
    - /asha               → ASHA worker dashboard APIs
    - /asha/dashboard     → ASHA web interface (HTML)
    - /doctor             → Doctor dashboard APIs
    - /ai                 → AI orchestration (placeholder)
    """
    from app.blueprints.telegram.routes import telegram_bp
    from app.blueprints.admin.routes import admin_bp
    from app.blueprints.admin_dashboard.routes import admin_dashboard_bp
    from app.blueprints.asha.routes import asha_bp
    from app.blueprints.asha_dashboard.routes import asha_dashboard_bp
    from app.blueprints.doctor.routes import doctor_bp
    from app.blueprints.doctor_dashboard import doctor_dashboard_bp
    from app.blueprints.ai.routes import ai_bp
    from app.blueprints.api.routes import api_bp
    from app.blueprints.shared_dashboard import shared_dashboard_bp
    
    # ASHA RAG Chatbot Blueprint
    from app.rag.api import asha_rag_bp
    
    app.register_blueprint(telegram_bp, url_prefix='/telegram')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(admin_dashboard_bp)  # Prefix defined in blueprint
    app.register_blueprint(asha_bp, url_prefix='/asha')
    app.register_blueprint(asha_dashboard_bp)  # Prefix defined in blueprint
    app.register_blueprint(doctor_bp, url_prefix='/doctor')
    app.register_blueprint(doctor_dashboard_bp)  # Prefix defined in blueprint
    app.register_blueprint(ai_bp, url_prefix='/ai')
    app.register_blueprint(api_bp)  # Prefix defined in blueprint (/api)
    
    # ASHA RAG API endpoints (/asha/rag/*)
    app.register_blueprint(asha_rag_bp)
    
    # Doctor AI Assistant API endpoints (/doctor/ai/*)
    from app.doctor.ai_api import doctor_ai_bp
    app.register_blueprint(doctor_ai_bp)
    
    # Auth blueprint (login / logout — root route)
    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)
    
    # Shared dashboard blueprint (Medical Exports, Unified Portfolio)
    app.register_blueprint(shared_dashboard_bp)


def register_error_handlers(app):
    """
    Register global error handlers for common HTTP errors.
    """
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Resource not found"}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        import traceback
        app.logger.error(f"Internal Server Error: {error}")
        app.logger.error(traceback.format_exc())
        return {"error": "Internal server error"}, 500


def register_route_protection(app):
    """
    Protect dashboard routes with session-based auth.
    API routes (/admin/analytics, /asha/mothers, etc.) are left open for now
    because the Telegram bot and AJAX calls depend on them.
    Only the HTML dashboard routes require login.
    """
    from flask import session, redirect, url_for, request as flask_request

    PROTECTED_PREFIXES = [
        '/admin/dashboard',
        '/asha/dashboard',
        '/doctor/dashboard',
        '/dashboard/shared',
    ]

    ROLE_MAP = {
        '/admin/dashboard': 'admin',
        '/asha/dashboard': 'asha',
        '/doctor/dashboard': 'doctor',
    }

    @app.before_request
    def check_dashboard_auth():
        path = flask_request.path

        # Only protect dashboard HTML routes
        for prefix in PROTECTED_PREFIXES:
            if path.startswith(prefix):
                if not session.get('logged_in'):
                    return redirect(url_for('auth.login'))
                # Check role matches the dashboard being accessed
                # Shared dashboard allows both asha and doctor
                required_role = ROLE_MAP.get(prefix)
                user_role = session.get('role')
                
                if prefix == '/dashboard/shared':
                    if user_role not in ['asha', 'doctor']:
                        return redirect(url_for('auth.login'))
                elif required_role and user_role != required_role:
                    return redirect(url_for('auth.login'))
                break
