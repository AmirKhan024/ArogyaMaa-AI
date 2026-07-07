"""
Authentication Blueprint

Handles login/logout and session-based security for the web dashboards.
Uses Flask session to track authenticated users by role.

Credentials are verified against bcrypt password hashes stored in Postgres
(seed demo users with db/seed.py). An optional static "evaluator" admin login is
available ONLY in development, using ADMIN_USERNAME / ADMIN_PASSWORD from the env.
"""

import logging
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for, session,
    current_app, jsonify,
)

from app.repositories import asha_repo, doctors_repo
from app.security import verify_password

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    """Landing page with login form. POST validates credentials against the DB."""
    if session.get('logged_in'):
        return _redirect_by_role(session.get('role'))

    error = None
    if request.method == 'POST':
        raw_username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # 1. Optional dev-only evaluator admin (no admins table in this prototype).
        if _try_dev_admin(raw_username, password):
            return _redirect_by_role('admin')

        # 2. Doctor (DB, bcrypt-verified)
        doctor = doctors_repo.get_by_username(raw_username)
        if doctor and doctor.get('active', True) and verify_password(password, doctor.get('password_hash')):
            session['logged_in'] = True
            session['username'] = doctor.get('username', raw_username)
            session['role'] = 'doctor'
            session['doctor_id'] = str(doctor['_id'])
            session['display_name'] = doctor.get('name', 'Doctor')
            return _redirect_by_role('doctor')

        # 3. ASHA worker (DB, bcrypt-verified)
        asha = asha_repo.get_by_username(raw_username)
        if asha and asha.get('active', True) and verify_password(password, asha.get('password_hash')):
            session['logged_in'] = True
            session['username'] = asha.get('username', raw_username)
            session['role'] = 'asha'
            session['asha_id'] = str(asha['_id'])
            session['display_name'] = asha.get('name', 'ASHA Worker')
            return _redirect_by_role('asha')

        error = 'Invalid username or password'

    return render_template('index.html', error=error)


@auth_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('auth.login'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_dev_admin(username, password):
    """
    Development-only static admin login. Returns True (and sets the session) when
    APP_ENV == 'development' and the env-configured admin credentials match.
    Never active in production; no hardcoded password.
    """
    if str(current_app.config.get('APP_ENV', 'development')).lower() != 'development':
        return False
    admin_user = current_app.config.get('ADMIN_USERNAME') or 'admin'
    admin_pass = current_app.config.get('ADMIN_PASSWORD')  # set in .env for dev demos
    if not admin_pass:
        return False
    if username.lower() == str(admin_user).lower() and password == admin_pass:
        session['logged_in'] = True
        session['username'] = admin_user
        session['role'] = 'admin'
        session['display_name'] = 'Administrator'
        return True
    return False


def _redirect_by_role(role):
    """Redirect to the correct dashboard based on user role."""
    if role == 'admin':
        return redirect(url_for('admin_dashboard.dashboard'))
    elif role == 'doctor':
        doctor_id = session.get('doctor_id', '')
        return redirect(url_for('doctor_dashboard.dashboard', doctor_id=doctor_id))
    elif role == 'asha':
        asha_id = session.get('asha_id', '')
        return redirect(url_for('asha_dashboard.dashboard', asha_id=asha_id))
    return redirect(url_for('auth.login'))


# ── Decorators for route protection ──────────────────────────────────────────

def login_required(f):
    """Decorator: redirects to login if not authenticated (HTML routes)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    """Decorator factory: requires a specific role (HTML routes)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('auth.login'))
            if session.get('role') != role:
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def api_login_required(f):
    """
    Decorator for JSON API routes returning/mutating patient data.

    Allows either a logged-in session OR a server-to-server call carrying the
    X-Internal-Token header equal to INTERNAL_API_TOKEN (used by the Telegram bot).
    Returns 401 JSON otherwise.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('logged_in'):
            return f(*args, **kwargs)
        token = request.headers.get('X-Internal-Token')
        internal = current_app.config.get('INTERNAL_API_TOKEN')
        if token and internal and token == internal:
            return f(*args, **kwargs)
        return jsonify({"error": "unauthorized"}), 401
    return decorated
