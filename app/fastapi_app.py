"""
ArogyaMaa FastAPI Application

FastAPI port of the Flask app factory (app/__init__.py). Route surface,
auth behavior, error bodies and the PWA contract are kept byte-identical;
see MIGRATION_NOTES.md.

Endpoints are plain `def` functions on purpose: FastAPI runs them in its
threadpool, which is what we want for the synchronous SQLAlchemy/psycopg
repositories and the sync Groq SDK.
"""

import logging
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from app.web_settings import settings
from app.db import init_db
from app.routers._auth_guard import auth_guard
from app.routers._templating import init_templating

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

_APP_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def _lifespan(app):
    init_db(None)
    yield


def create_fastapi_app():
    # Docs/openapi disabled: the public route surface must stay identical to
    # the Flask app's.
    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan
    )

    # Middleware order matters: add_middleware prepends (last added runs
    # outermost), so the auth guard is added FIRST and SessionMiddleware
    # SECOND — that way sessions are decoded before the guard runs.
    app.middleware("http")(auth_guard)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        session_cookie="session",
        same_site="lax",
        https_only=False,
        max_age=None,  # browser-session cookie, like Flask's default
    )

    app.mount("/static", StaticFiles(directory=os.path.join(_APP_DIR, "static")), name="static-mount")

    @app.get("/sw.js")
    def service_worker():
        # PWA: the service worker must be served from the root with
        # Service-Worker-Allowed so its scope can cover /asha/*.
        return FileResponse(
            os.path.join(_APP_DIR, "static", "js", "sw.js"),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc):
        if exc.status_code == 404:
            return JSONResponse({"error": "Resource not found"}, status_code=404)
        detail = exc.detail if isinstance(exc.detail, str) else "Error"
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        # 400, never 422: the offline queue client drops items on exactly 400
        # and retries forever on anything else.
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        logger.error("Internal Server Error: %s", exc)
        logger.error(traceback.format_exc())
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    _register_routers(app)
    init_templating(app)
    return app


def _register_routers(app):
    # Routers are added here as they are ported, lowest-risk first.
    from app.routers import api, auth, admin, admin_dashboard, asha_dashboard, doctor_dashboard, shared_dashboard

    app.include_router(api.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(admin_dashboard.router)
    app.include_router(asha_dashboard.router)
    app.include_router(doctor_dashboard.router)
    app.include_router(shared_dashboard.router)


app = create_fastapi_app()
