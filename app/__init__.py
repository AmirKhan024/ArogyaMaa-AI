"""
ArogyaMaa Flask Application Factory

This module implements the Flask app factory pattern.
It creates and configures the Flask application with all necessary blueprints.
"""

import logging
import os

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

    # Root logging configuration (idempotent across factory calls).
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    # Load configuration from config.py (which reads .env)
    config = get_config(config_name)
    app.config.from_object(config)

    # SECRET_KEY is REQUIRED — fail fast rather than silently inventing one.
    if not app.config.get('SECRET_KEY'):
        raise RuntimeError(
            "SECRET_KEY is not set. Add it to .env "
            "(generate: python -c \"import secrets;print(secrets.token_hex(32))\")."
        )

    # Initialize the database connection (Supabase / Postgres)
    with app.app_context():
        init_db(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register route protection
    register_route_protection(app)

    # PWA: serve the service worker from the app root so its scope can cover /asha/*.
    register_pwa(app)

    return app


def register_pwa(app):
    """
    Serve the ASHA offline PWA's service worker from the root path.

    A service worker can only control pages at or below the path it is served from, so the
    file physically living in ``app/static/js/sw.js`` must also be reachable at ``/sw.js``
    with the ``Service-Worker-Allowed: /`` header to control the whole origin (the ASHA
    dashboard lives under ``/asha/dashboard``). This path matches no protected prefix, so the
    central auth guard leaves it public automatically.
    """
    from flask import send_from_directory, make_response

    @app.route('/sw.js')
    def service_worker():
        js_dir = os.path.join(app.static_folder, 'js')
        resp = make_response(send_from_directory(js_dir, 'sw.js'))
        resp.headers['Content-Type'] = 'application/javascript'
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp


def register_blueprints(app):
    """
    Register all Flask blueprints with their URL prefixes.
    
    Blueprint structure:
    - /admin              → Admin dashboard APIs
    - /admin/dashboard    → Admin web interface (HTML)
    - /asha               → ASHA worker dashboard APIs
    - /asha/dashboard     → ASHA web interface (HTML)
    - /doctor             → Doctor dashboard APIs
    - /ai                 → AI orchestration (placeholder)
    """
    from app.blueprints.admin.routes import admin_bp
    from app.blueprints.admin_dashboard.routes import admin_dashboard_bp
    from app.blueprints.asha.routes import asha_bp
    from app.blueprints.asha_dashboard.routes import asha_dashboard_bp
    from app.blueprints.doctor.routes import doctor_bp
    from app.blueprints.doctor_dashboard import doctor_dashboard_bp
    from app.blueprints.api.routes import api_bp
    from app.blueprints.shared_dashboard import shared_dashboard_bp
    
    # ASHA RAG Chatbot Blueprint
    from app.rag.api import asha_rag_bp
    
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(admin_dashboard_bp)  # Prefix defined in blueprint
    app.register_blueprint(asha_bp, url_prefix='/asha')
    app.register_blueprint(asha_dashboard_bp)  # Prefix defined in blueprint
    app.register_blueprint(doctor_bp, url_prefix='/doctor')
    app.register_blueprint(doctor_dashboard_bp)  # Prefix defined in blueprint
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
    Session-based auth enforced centrally in a single before_request hook:

    1. HTML dashboard routes → redirect to login (and role-check) if not authenticated.
    2. JSON API routes that read/mutate patient data → 401 unless there is a logged-in
       session OR a valid X-Internal-Token (server-to-server, e.g. the Telegram bot).

    Health checks and the auth/login routes stay public.
    """
    from flask import session, redirect, url_for, jsonify, request as flask_request

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

    # JSON API prefixes that must not be world-readable.
    API_PROTECTED_PREFIXES = ('/admin', '/asha', '/doctor', '/api', '/ai')

    def _api_authorized():
        if session.get('logged_in'):
            return True
        token = flask_request.headers.get('X-Internal-Token')
        internal = app.config.get('INTERNAL_API_TOKEN')
        return bool(token and internal and token == internal)

    @app.before_request
    def check_auth():
        path = flask_request.path

        # 1. Dashboard HTML routes → redirect + role check
        for prefix in PROTECTED_PREFIXES:
            if path.startswith(prefix):
                if not session.get('logged_in'):
                    return redirect(url_for('auth.login'))
                required_role = ROLE_MAP.get(prefix)
                user_role = session.get('role')
                if prefix == '/dashboard/shared':
                    if user_role not in ['asha', 'doctor']:
                        return redirect(url_for('auth.login'))
                elif required_role and user_role != required_role:
                    return redirect(url_for('auth.login'))
                return None  # dashboard auth handled

        # 2. JSON API routes → 401 unless session or internal token
        if path.startswith(API_PROTECTED_PREFIXES) and not path.endswith('/health'):
            if not _api_authorized():
                return jsonify({"error": "unauthorized"}), 401
        return None
