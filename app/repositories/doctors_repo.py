"""
Doctor Repository

Data access layer for the 'doctors' table (Postgres).
Function names, signatures, and return shapes preserved from the MongoDB version.
"""

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, update_by_id, utcnow,
)

_KNOWN = {
    "username", "password_hash", "name", "specialization", "phone", "qualification",
    "hospital", "availability", "active", "assigned_mothers", "performance_stats", "joined_at",
}
_JSONB = {"availability", "assigned_mothers", "performance_stats"}

_DEFAULT_STATS = {
    "total_consultations": 0,
    "high_risk_cases_handled": 0,
    "average_response_time_hours": 0.0,
}


def create(doctor_data):
    """Create a new doctor profile. Returns the new id (str)."""
    doctor_data.setdefault("assigned_mothers", [])
    doctor_data.setdefault("performance_stats", dict(_DEFAULT_STATS))
    doctor_data.setdefault("joined_at", utcnow())
    doctor_data.setdefault("active", True)
    return insert_row("doctors", doctor_data, known_cols=_KNOWN, jsonb_cols=_JSONB)


def get_by_id(doctor_id):
    return fetch_one("select * from doctors where id = cast(:id as uuid)", {"id": str(doctor_id)})


find_by_id = get_by_id


def get_by_phone(phone):
    return fetch_one("select * from doctors where phone = :phone", {"phone": phone})


def get_by_username(username):
    """Case-insensitive username lookup (used by auth + admin duplicate checks)."""
    return fetch_one("select * from doctors where lower(username) = lower(:u)", {"u": username})


def list_all_active():
    return fetch_all("select * from doctors where active = true order by joined_at")


def list_all():
    return fetch_all("select * from doctors order by joined_at")


def list_by_specialization(specialization):
    return fetch_all(
        "select * from doctors where specialization = :s and active = true order by joined_at",
        {"s": specialization},
    )


def update(doctor_id, update_data):
    return update_by_id("doctors", doctor_id, update_data, known_cols=_KNOWN, jsonb_cols=_JSONB)


def add_mother_assignment(doctor_id, mother_id):
    row = get_by_id(doctor_id)
    if not row:
        return False
    ids = [str(x) for x in (row.get("assigned_mothers") or [])]
    if str(mother_id) in ids:
        return False
    ids.append(str(mother_id))
    return update(doctor_id, {"assigned_mothers": ids})


def remove_mother_assignment(doctor_id, mother_id):
    row = get_by_id(doctor_id)
    if not row:
        return False
    ids = [str(x) for x in (row.get("assigned_mothers") or []) if str(x) != str(mother_id)]
    return update(doctor_id, {"assigned_mothers": ids})


def increment_consultation_count(doctor_id, is_high_risk=False):
    row = get_by_id(doctor_id)
    if not row:
        return False
    stats = dict(row.get("performance_stats") or _DEFAULT_STATS)
    stats["total_consultations"] = (stats.get("total_consultations") or 0) + 1
    if is_high_risk:
        stats["high_risk_cases_handled"] = (stats.get("high_risk_cases_handled") or 0) + 1
    return update(doctor_id, {"performance_stats": stats})


def deactivate(doctor_id):
    return update(doctor_id, {"active": False})
