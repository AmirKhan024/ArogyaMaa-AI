"""
Auth Router — FastAPI port of app/blueprints/auth/__init__.py.

Login/logout and session handling. Credentials verified against bcrypt hashes
in Postgres; optional dev-only static admin login via ADMIN_USERNAME/PASSWORD.
"""

import logging

from fastapi import APIRouter, Form, Request
from starlette.responses import RedirectResponse

from app.repositories import asha_repo, doctors_repo
from app.security import verify_password
from app.web_settings import settings
from app.routers._templating import render, flask_url_for

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", name="auth.login")
def login_page(request: Request):
    if request.session.get('logged_in'):
        return _redirect_by_role(request, request.session.get('role'))
    return render(request, 'index.html', error=None)


@router.post("/")
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    if request.session.get('logged_in'):
        return _redirect_by_role(request, request.session.get('role'))

    raw_username = username.strip()

    # 1. Optional dev-only evaluator admin (no admins table in this prototype).
    if _try_dev_admin(request, raw_username, password):
        return _redirect_by_role(request, 'admin')

    # 2. Doctor (DB, bcrypt-verified)
    doctor = doctors_repo.get_by_username(raw_username)
    if doctor and doctor.get('active', True) and verify_password(password, doctor.get('password_hash')):
        request.session['logged_in'] = True
        request.session['username'] = doctor.get('username', raw_username)
        request.session['role'] = 'doctor'
        request.session['doctor_id'] = str(doctor['_id'])
        request.session['display_name'] = doctor.get('name', 'Doctor')
        return _redirect_by_role(request, 'doctor')

    # 3. ASHA worker (DB, bcrypt-verified)
    asha = asha_repo.get_by_username(raw_username)
    if asha and asha.get('active', True) and verify_password(password, asha.get('password_hash')):
        request.session['logged_in'] = True
        request.session['username'] = asha.get('username', raw_username)
        request.session['role'] = 'asha'
        request.session['asha_id'] = str(asha['_id'])
        request.session['display_name'] = asha.get('name', 'ASHA Worker')
        return _redirect_by_role(request, 'asha')

    return render(request, 'index.html', error='Invalid username or password')


@router.get("/logout", name="auth.logout")
def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(flask_url_for('auth.login'), status_code=302)


def _try_dev_admin(request, username, password):
    """Development-only static admin login (never active in production)."""
    if str(settings.APP_ENV or 'development').lower() != 'development':
        return False
    admin_user = settings.ADMIN_USERNAME or 'admin'
    admin_pass = settings.ADMIN_PASSWORD  # set in .env for dev demos
    if not admin_pass:
        return False
    if username.lower() == str(admin_user).lower() and password == admin_pass:
        request.session['logged_in'] = True
        request.session['username'] = admin_user
        request.session['role'] = 'admin'
        request.session['display_name'] = 'Administrator'
        return True
    return False


def _redirect_by_role(request, role):
    """Redirect to the correct dashboard based on user role."""
    if role == 'admin':
        return RedirectResponse(flask_url_for('admin_dashboard.dashboard'), status_code=302)
    elif role == 'doctor':
        doctor_id = request.session.get('doctor_id', '')
        return RedirectResponse(flask_url_for('doctor_dashboard.dashboard', doctor_id=doctor_id), status_code=302)
    elif role == 'asha':
        asha_id = request.session.get('asha_id', '')
        return RedirectResponse(flask_url_for('asha_dashboard.dashboard', asha_id=asha_id), status_code=302)
    return RedirectResponse(flask_url_for('auth.login'), status_code=302)
