"""
API Blueprint

General API endpoints for document access and other cross-cutting features.
"""

from flask import Blueprint

# Import routes will be added when routes.py is created
from .routes import api_bp

__all__ = ['api_bp']
