"""
Admin Dashboard Blueprint

Provides web interface for system administrators to:
- View system analytics and KPIs
- Manage mother-ASHA-doctor assignments
- Monitor ASHA worker performance
- Track doctor workload

URL Prefix: /admin/dashboard
"""

from .routes import admin_dashboard_bp

__all__ = ['admin_dashboard_bp']
