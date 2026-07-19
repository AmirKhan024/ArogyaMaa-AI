"""
ArogyaMaa web app — FastAPI/uvicorn entry point.

Local (Windows) dev:
    python run_fastapi.py                    # port 8000 (the main web app)
    FASTAPI_PORT=8001 python run_fastapi.py  # side-by-side with legacy Flask

Notes for Windows: gunicorn is fork-based and does not run here. Multiple
uvicorn workers use spawn — each worker builds its own DB engine (pool x
workers connections against Supabase) and --reload is incompatible with
workers>1. Default is 1 worker for dev.

Linux / Docker production form:
    gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.fastapi_app:app
"""

import os

import uvicorn

from app.web_settings import settings


def main():
    port = int(os.getenv("FASTAPI_PORT", 8000))
    workers = int(os.getenv("WEB_CONCURRENCY", 1))
    print("Starting ArogyaMaa (FastAPI) on %s:%d (workers=%d)" % (settings.HOST, port, workers))
    uvicorn.run(
        "app.fastapi_app:app",
        host=settings.HOST,
        port=port,
        workers=workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
