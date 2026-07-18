"""
Postgres (Supabase) Connection Layer — SQLAlchemy Core.

Replaces the previous MongoDB/pymongo layer. A single SQLAlchemy Engine is shared
across the whole application (Flask web process AND the standalone Telegram bot
process). All data access goes through the repositories in app/repositories/, which
use the helpers exposed here.

Back-compat contract (so existing blueprints need only mechanical changes):
  - Repository read helpers return plain dicts with a STRING ``_id`` key aliased from
    the Postgres ``id`` UUID, because downstream code does ``str(doc['_id'])`` and
    stores ids in the Flask session.
  - All UUID values are stringified so equality checks and jsonify() keep working.
"""

import os
import json
import uuid as _uuid
from datetime import date, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Global SQLAlchemy engine (initialized once, lazily)
_engine: Engine | None = None


def _resolve_database_url(app=None) -> str:
    url = (app.config.get("DATABASE_URL") if app is not None else None) or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at your Supabase pooler URI "
            "(postgresql+psycopg://...:6543/postgres) or a local Postgres."
        )
    return url


def init_db(app=None) -> Engine:
    """
    Initialize the Postgres connection.

    Called once during app startup in the app factory, and also usable standalone
    (e.g. from run_telegram_bot.py) by passing app=None. Idempotent.

    Args:
        app: Flask application instance (optional). If given, config + logger are used.

    Returns:
        The shared SQLAlchemy Engine.
    """
    global _engine

    if _engine is None:
        url = _resolve_database_url(app)
        # prepare_threshold=None disables psycopg3 server-side prepared statements.
        # Required with Supabase's transaction-mode pooler (PgBouncer, port 6543):
        # pooled server connections are shared across clients, so named prepared
        # statements collide with "DuplicatePreparedStatement" errors.
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            future=True,
            connect_args={"prepare_threshold": None},
        )
        # Smoke-test the connection so failures surface at startup, not first query.
        with _engine.connect() as conn:
            conn.exec_driver_sql("select 1")
        if app is not None:
            app.logger.info("✓ Supabase Postgres connected")

    return _engine


def get_engine() -> Engine:
    """Return the shared Engine, initializing lazily if needed."""
    global _engine
    if _engine is None:
        init_db(None)
    return _engine


# ── Row -> dict helpers ────────────────────────────────────────────────────────

def _clean_value(v):
    """Stringify UUIDs so equality checks + JSON serialization keep working."""
    if isinstance(v, _uuid.UUID):
        return str(v)
    return v


def _map_row(row_mapping) -> dict:
    d = {k: _clean_value(v) for k, v in row_mapping.items()}
    # Flatten the `extra` JSONB catch-all to top level so fields without a dedicated
    # column (location, edd, danger_signs, substance_usage, preferred_language, ...)
    # are readable at the root, matching what callers expect. Real columns always win
    # on key conflicts; `extra` itself stays available for debugging.
    extra = d.get("extra")
    if isinstance(extra, dict) and extra:
        for k, v in extra.items():
            if d.get(k) is None:  # real columns win only when they hold a value
                d[k] = _clean_value(v)
    # Alias the PK to a string '_id' for back-compat with the old pymongo code.
    if "id" in d and "_id" not in d:
        d["_id"] = str(d["id"])
    return d


def rows_to_dicts(result) -> list[dict]:
    """Map a SQLAlchemy Result to a list of back-compat dicts."""
    return [_map_row(row) for row in result.mappings()]


def row_to_dict(result) -> dict | None:
    """Map the first row of a Result to a dict, or None if empty."""
    rows = rows_to_dicts(result)
    return rows[0] if rows else None


# ── JSONB helpers ──────────────────────────────────────────────────────────────

class _JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, _uuid.UUID):
            return str(o)
        return super().default(o)


def to_jsonb(value):
    """
    Serialize a Python value for insertion into a JSONB column.

    Use together with a ``:param`` bound to this and a ``cast(:param as jsonb)`` (or
    ``:param::jsonb``) in the SQL, e.g.::

        conn.execute(text("insert into t (data) values (cast(:data as jsonb))"),
                     {"data": to_jsonb(payload)})

    Returns None for None so a NULL is stored rather than the string 'null'.
    """
    if value is None:
        return None
    return json.dumps(value, cls=_JSONEncoder)


def new_uuid() -> str:
    """Generate a new UUID string (for client-side ids / tests)."""
    return str(_uuid.uuid4())
