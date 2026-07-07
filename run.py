"""
ArogyaMaa Application Entry Point

This script starts the Flask development server.
It uses the app factory pattern to create the application instance.
"""

import logging
import os
import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from app import create_app

logger = logging.getLogger(__name__)

# Determine environment from .env or default to development
env = os.getenv('APP_ENV', 'development')

# Create Flask app using factory
app = create_app(config_name=env)

if __name__ == '__main__':
    # Get host and port from config
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 5000)
    debug = app.config.get('DEBUG', True)
    
    logger.info(
        "ArogyaMaa backend starting | env=%s | http://%s:%s", env, host, port
    )

    app.run(host=host, port=port, debug=debug)
