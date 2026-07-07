"""
Mother Repository

Data access layer for the 'mothers' table (Postgres).
Handles all CRUD operations for mother profiles. Public function names, signatures,
and return shapes are preserved from the previous MongoDB implementation:
reads return dicts with a string ``_id`` key; ``create`` returns the new id (str).
"""

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, update_by_id, update_where, utcnow,
)

_KNOWN = {
    "telegram_chat_id", "telegram_username", "name", "age", "phone", "risk_level",
    "assigned_asha_id", "assigned_doctor_id", "medical_history", "current_pregnancy",
    "address", "registered_at", "last_active", "active",
}
_JSONB = {"medical_history", "current_pregnancy", "address"}
_UUID = {"assigned_asha_id", "assigned_doctor_id"}


def create(mother_data):
    """Create a new mother profile. Returns the new id (str)."""
    mother_data.setdefault("registered_at", utcnow())
    mother_data.setdefault("last_active", utcnow())
    mother_data.setdefault("active", True)
    return insert_row(
        "mothers", mother_data,
        known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID, extra_col="extra",
    )


def get_by_id(mother_id):
    """Get a mother by id. Returns dict or None."""
    return fetch_one("select * from mothers where id = cast(:id as uuid)", {"id": str(mother_id)})


# Alias for consistency
find_by_id = get_by_id


def get_by_telegram_chat_id(telegram_chat_id):
    """Get a mother by Telegram chat ID (stored as text). Returns dict or None."""
    return fetch_one(
        "select * from mothers where telegram_chat_id = :cid",
        {"cid": str(telegram_chat_id)},
    )


def list_by_asha(asha_id):
    """List active mothers assigned to a specific ASHA worker."""
    return fetch_all(
        "select * from mothers where assigned_asha_id = cast(:aid as uuid) and active = true "
        "order by registered_at desc",
        {"aid": str(asha_id)},
    )


def list_by_doctor(doctor_id):
    """List active mothers assigned to a specific doctor."""
    return fetch_all(
        "select * from mothers where assigned_doctor_id = cast(:did as uuid) and active = true "
        "order by registered_at desc",
        {"did": str(doctor_id)},
    )


def list_all_active():
    """List all active mothers."""
    return fetch_all("select * from mothers where active = true order by registered_at desc")


def update(mother_id, update_data):
    """Update a mother's profile (also refreshes last_active). Returns bool."""
    update_data = dict(update_data)
    update_data["last_active"] = utcnow()
    return update_by_id(
        "mothers", mother_id, update_data,
        known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID, extra_col="extra",
    )


def assign_asha(mother_id, asha_id):
    """Assign an ASHA worker to a mother."""
    return update(mother_id, {"assigned_asha_id": str(asha_id)})


def assign_doctor(mother_id, doctor_id):
    """Assign a doctor to a mother."""
    return update(mother_id, {"assigned_doctor_id": str(doctor_id)})


def deactivate(mother_id):
    """Deactivate a mother (e.g., after delivery)."""
    return update(mother_id, {"active": False})
