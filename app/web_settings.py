"""
Settings access for the FastAPI app.

Reuses the existing config classes in app/config.py (which read .env) but as
plain attribute access instead of Flask's app.config mapping. The returned
object is the config CLASS, so attributes are runtime-mutable — tests rely on
toggling settings.ENABLE_AI_ADVISORY, mirroring the Flask test's
app.config mutation.
"""

import os

from app.config import get_config

settings = get_config(os.getenv("APP_ENV", "development"))

# SECRET_KEY is REQUIRED — fail fast rather than silently inventing one.
if not settings.SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set. Add it to .env "
        "(generate: python -c \"import secrets;print(secrets.token_hex(32))\")."
    )
