"""
ASHA Dashboard Blueprint

Provides web interface for ASHA workers to:
- View assigned mothers
- Submit health assessments
- Track their performance statistics

URL Prefix: /asha/dashboard
"""

from .routes import asha_dashboard_bp

__all__ = ['asha_dashboard_bp']
