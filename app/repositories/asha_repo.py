"""
ASHA Worker Repository

Data access layer for the 'asha_workers' table (Postgres).
Function names, signatures, and return shapes preserved from the MongoDB version.
"""

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, update_by_id, utcnow,
)

_KNOWN = {
    "username", "password_hash", "name", "phone", "area", "district", "state",
    "active", "assigned_mothers", "performance_stats", "joined_at",
}
_JSONB = {"assigned_mothers", "performance_stats"}

_DEFAULT_STATS = {
    "total_assessments": 0,
    "high_risk_detected": 0,
    "moderate_risk_detected": 0,
    "low_risk_detected": 0,
    "average_assessments_per_week": 0.0,
    "last_assessment_date": None,
}


def create(asha_data):
    """Create a new ASHA worker profile. Returns the new id (str)."""
    asha_data.setdefault("assigned_mothers", [])
    asha_data.setdefault("performance_stats", dict(_DEFAULT_STATS))
    asha_data.setdefault("joined_at", utcnow())
    asha_data.setdefault("active", True)
    return insert_row("asha_workers", asha_data, known_cols=_KNOWN, jsonb_cols=_JSONB)


def get_by_id(asha_id):
    return fetch_one("select * from asha_workers where id = cast(:id as uuid)", {"id": str(asha_id)})


find_by_id = get_by_id


def get_by_phone(phone):
    return fetch_one("select * from asha_workers where phone = :phone", {"phone": phone})


def get_by_username(username):
    """Case-insensitive username lookup (used by auth + admin duplicate checks)."""
    return fetch_one(
        "select * from asha_workers where lower(username) = lower(:u)", {"u": username}
    )


def list_all_active():
    return fetch_all("select * from asha_workers where active = true order by joined_at")


def list_all():
    return fetch_all("select * from asha_workers order by joined_at")


def list_by_area(area):
    return fetch_all(
        "select * from asha_workers where area = :area and active = true order by joined_at",
        {"area": area},
    )


def update(asha_id, update_data):
    return update_by_id("asha_workers", asha_id, update_data, known_cols=_KNOWN, jsonb_cols=_JSONB)


def add_mother_assignment(asha_id, mother_id):
    """Add a mother id to assigned_mothers (JSONB array, de-duplicated)."""
    row = get_by_id(asha_id)
    if not row:
        return False
    ids = [str(x) for x in (row.get("assigned_mothers") or [])]
    if str(mother_id) in ids:
        return False
    ids.append(str(mother_id))
    return update(asha_id, {"assigned_mothers": ids})


def remove_mother_assignment(asha_id, mother_id):
    row = get_by_id(asha_id)
    if not row:
        return False
    ids = [str(x) for x in (row.get("assigned_mothers") or []) if str(x) != str(mother_id)]
    return update(asha_id, {"assigned_mothers": ids})


def increment_assessment_count(asha_id, risk_category):
    """Increment total + per-category counters inside performance_stats (JSONB)."""
    row = get_by_id(asha_id)
    if not row:
        return False
    field_map = {
        "LOW": "low_risk_detected",
        "MODERATE": "moderate_risk_detected",
        "HIGH": "high_risk_detected",
        "CRITICAL": "high_risk_detected",
    }
    field = field_map.get((risk_category or "").upper())
    if not field:
        return False
    stats = dict(row.get("performance_stats") or _DEFAULT_STATS)
    stats["total_assessments"] = (stats.get("total_assessments") or 0) + 1
    stats[field] = (stats.get(field) or 0) + 1
    stats["last_assessment_date"] = utcnow().isoformat()
    return update(asha_id, {"performance_stats": stats})


def deactivate(asha_id):
    return update(asha_id, {"active": False})
