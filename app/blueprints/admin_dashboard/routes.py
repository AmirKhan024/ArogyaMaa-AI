"""
Admin Dashboard Routes

Renders HTML pages for admin interface using Jinja2 templates.
Consumes data from /admin API endpoints.
"""

from flask import Blueprint, render_template, jsonify
import requests
import os

admin_dashboard_bp = Blueprint('admin_dashboard', __name__, url_prefix='/admin/dashboard')


@admin_dashboard_bp.route('/')
def dashboard():
    """Main admin dashboard with analytics and KPIs"""
    return render_template('admin/dashboard.html')


@admin_dashboard_bp.route('/mothers')
def mothers():
    """Mothers management page with assignment controls"""
    return render_template('admin/mothers.html')


@admin_dashboard_bp.route('/asha')
def asha():
    """ASHA workers overview page"""
    return render_template('admin/asha.html')


@admin_dashboard_bp.route('/doctors')
def doctors():
    """Doctors overview page"""
    return render_template('admin/doctors.html')
