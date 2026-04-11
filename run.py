"""
ArogyaMaa Application Entry Point

This script starts the Flask development server.
It uses the app factory pattern to create the application instance.
"""

import os
import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from app import create_app

# Determine environment from .env or default to development
env = os.getenv('APP_ENV', 'development')

# Create Flask app using factory
app = create_app(config_name=env)

if __name__ == '__main__':
    # Get host and port from config
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 5000)
    debug = app.config.get('DEBUG', True)
    
    print(f"""
    ╔═══════════════════════════════════════╗
    ║   ArogyaMaa Backend Server          ║
    ║   Environment: {env:24s} ║
    ║   Running on: http://{host}:{port}      ║
    ╚═══════════════════════════════════════╝
    
    Available endpoints:
    - /telegram/webhook   → Telegram bot webhook
    - /telegram/health    → Telegram service health
    - /admin/analytics    → Admin analytics
    - /admin/assign       → Assign workers
    - /asha/mothers       → ASHA assigned mothers
    - /asha/assessment    → Submit assessment
    - /asha/stats         → ASHA statistics
    - /doctor/mothers     → Doctor assigned mothers
    - /doctor/assessments → View assessments
    - /doctor/consultation → Submit consultation
    - /doctor/message     → Send message to mother
    - /ai/evaluate        → AI evaluation (placeholder)
    """)
    
    app.run(host=host, port=port, debug=debug)
