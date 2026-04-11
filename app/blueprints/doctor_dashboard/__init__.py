"""
Doctor Dashboard Blueprint

Provides web interface for doctors to review assessments and manage patients.
"""

from flask import Blueprint

doctor_dashboard_bp = Blueprint(
    'doctor_dashboard',
    __name__,
    url_prefix='/doctor/dashboard'
)

from . import routes
