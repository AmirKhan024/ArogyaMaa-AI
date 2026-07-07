"""
Shared SQLAlchemy Core helpers for the repository layer.

Keeps every repository thin and consistent: parameter binding everywhere (never
f-string interpolation into SQL), automatic JSONB serialization, UUID casting, and
an ``extra`` JSONB catch-all for Mongo fields that have no dedicated column.
"""

from datetime import datetime, timezone

from sqlalchemy import text

from app.db import get_engine, rows_to_dicts, row_to_dict, to_jsonb


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Low-level query helpers ────────────────────────────────────────────────────

def fetch_all(sql: str, params: dict | None = None) -> list[dict]:
    with get_engine().begin() as conn:
        res = conn.execute(text(sql), params or {})
        return rows_to_dicts(res)


def fetch_one(sql: str, params: dict | None = None) -> dict | None:
    with get_engine().begin() as conn:
        res = conn.execute(text(sql), params or {})
        return row_to_dict(res)


def exec_write(sql: str, params: dict | None = None) -> int:
    """Execute an INSERT/UPDATE/DELETE; return affected rowcount."""
    with get_engine().begin() as conn:
        res = conn.execute(text(sql), params or {})
        return res.rowcount or 0


def scalar(sql: str, params: dict | None = None):
    with get_engine().begin() as conn:
        return conn.execute(text(sql), params or {}).scalar()


# ── Generic INSERT / UPDATE with JSONB + extra handling ────────────────────────

def _expr(col: str, jsonb_cols: set, uuid_cols: set) -> str:
    if col in jsonb_cols:
        return f"cast(:{col} as jsonb)"
    if col in uuid_cols:
        return f"cast(:{col} as uuid)"
    return f":{col}"


def insert_row(
    table: str,
    data: dict,
    *,
    known_cols: set | None = None,
    jsonb_cols: set = frozenset(),
    uuid_cols: set = frozenset(),
    extra_col: str | None = None,
    returning: str = "id",
) -> str:
    """
    Insert a row. Keys not in ``known_cols`` are folded into ``extra_col`` (a JSONB
    column) instead of being dropped. Returns the ``returning`` column as a string.
    """
    jsonb_cols = set(jsonb_cols)
    uuid_cols = set(uuid_cols)
    if extra_col:
        jsonb_cols.add(extra_col)

    cols: list[str] = []
    params: dict = {}
    extra_payload: dict = {}

    for k, v in data.items():
        if known_cols is not None and k not in known_cols:
            extra_payload[k] = v
            continue
        cols.append(k)
        params[k] = to_jsonb(v) if k in jsonb_cols else v

    if extra_col and extra_payload:
        cols.append(extra_col)
        params[extra_col] = to_jsonb(extra_payload)

    col_list = ", ".join(cols)
    val_list = ", ".join(_expr(c, jsonb_cols, uuid_cols) for c in cols)
    sql = f"insert into {table} ({col_list}) values ({val_list}) returning {returning}"
    return str(scalar(sql, params))


def update_where(
    table: str,
    where_sql: str,
    where_params: dict,
    data: dict,
    *,
    known_cols: set | None = None,
    jsonb_cols: set = frozenset(),
    uuid_cols: set = frozenset(),
    extra_col: str | None = None,
) -> bool:
    """
    Update rows matching ``where_sql``. Unknown keys merge into ``extra_col`` JSONB
    (``extra = coalesce(extra,'{}') || delta``). Returns True if a row changed.
    """
    jsonb_cols = set(jsonb_cols)
    uuid_cols = set(uuid_cols)

    sets: list[str] = []
    params: dict = dict(where_params)
    extra_payload: dict = {}

    for k, v in data.items():
        if known_cols is not None and k not in known_cols:
            extra_payload[k] = v
            continue
        sets.append(f"{k} = {_expr(k, jsonb_cols, uuid_cols)}")
        params[k] = to_jsonb(v) if k in jsonb_cols else v

    if extra_col and extra_payload:
        sets.append(f"{extra_col} = coalesce({extra_col}, '{{}}'::jsonb) || cast(:__extra_delta as jsonb)")
        params["__extra_delta"] = to_jsonb(extra_payload)

    if not sets:
        return False

    sql = f"update {table} set {', '.join(sets)} where {where_sql}"
    return exec_write(sql, params) > 0


def update_by_id(table: str, id_value, data: dict, **kwargs) -> bool:
    return update_where(
        table,
        "id = cast(:__id as uuid)",
        {"__id": str(id_value)},
        data,
        **kwargs,
    )
