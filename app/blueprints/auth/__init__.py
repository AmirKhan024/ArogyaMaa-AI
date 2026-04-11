"""
Authentication Blueprint

Handles login/logout and session-based security for the web dashboards.
Uses Flask session to track authenticated users by role.

Mock credentials (evaluator mode):
  - admin / admin123  → Admin dashboard
  - doctor / pass123  → Doctor dashboard (first doctor from DB)
  - asha / pass123    → ASHA dashboard (first ASHA from DB)
"""

from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

auth_bp = Blueprint('auth', __name__)

# ── Mock credentials ──────────────────────────────────────────────────────────
# In production, replace with proper user table + hashed passwords
MOCK_USERS = {
    'admin':  {'password': 'admin123', 'role': 'admin'},
    'doctor': {'password': 'pass123',  'role': 'doctor'},
    'asha':   {'password': 'pass123',  'role': 'asha'},
}


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    """Landing page with login form. POST validates credentials."""
    # If already logged in, redirect to appropriate dashboard
    if session.get('logged_in'):
        return _redirect_by_role(session.get('role'))

    error = None
    if request.method == 'POST':
        raw_username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # 1. Check Mock Users (Admin/Static fallback)
        username_lower = raw_username.lower()
        user = MOCK_USERS.get(username_lower)
        if user and user['password'] == password:
            session['logged_in'] = True
            session['username'] = username_lower
            session['role'] = user['role']
            _resolve_user_id(user['role'])
            return _redirect_by_role(user['role'])
        
        # 2. Check Database for Doctors
        # Case insensitive regex match for username to prevent capitalization errors
        import re
        username_regex = re.compile(f'^{re.escape(raw_username)}$', re.IGNORECASE)
        
        from app.db import get_collection
        doctor = get_collection('doctors').find_one({
            'username': username_regex,
            'password': password,
            'active': True
        })
        if doctor:
            session['logged_in'] = True
            session['username'] = doctor.get('username', raw_username) # Store actual casing
            session['role'] = 'doctor'
            session['doctor_id'] = str(doctor['_id'])
            session['display_name'] = doctor.get('name', 'Doctor')
            return _redirect_by_role('doctor')
            
        # 3. Check Database for ASHA Workers
        asha = get_collection('asha_workers').find_one({
            'username': username_regex,
            'password': password,
            'active': True
        })
        if asha:
            session['logged_in'] = True
            session['username'] = asha.get('username', raw_username)
            session['role'] = 'asha'
            session['asha_id'] = str(asha['_id'])
            session['display_name'] = asha.get('name', 'ASHA Worker')
            return _redirect_by_role('asha')

        # Invalid credentials
        error = 'Invalid username or password'

    return render_template('index.html', error=error)


@auth_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for('auth.login'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_user_id(role):
    """Look up the first doctor/asha from MongoDB and store their ID in session."""
    try:
        if role == 'doctor':
            from app.repositories import doctors_repo
            doctors = doctors_repo.list_all()
            if doctors:
                session['doctor_id'] = str(doctors[0]['_id'])
                session['display_name'] = doctors[0].get('name', 'Doctor')
        elif role == 'asha':
            from app.repositories import asha_repo
            workers = asha_repo.list_all()
            if workers:
                session['asha_id'] = str(workers[0]['_id'])
                session['display_name'] = workers[0].get('name', 'ASHA Worker')
        elif role == 'admin':
            session['display_name'] = 'Administrator'
    except Exception:
        pass


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
    """Decorator: redirects to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    """Decorator factory: requires a specific role."""
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
