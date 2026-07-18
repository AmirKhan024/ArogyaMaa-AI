"""
Appointment storage (Postgres).

Formerly an Excel/openpyxl workbook; now backed by the Supabase ``appointments`` table.
Public function names and signatures are preserved so the rest of the appointment module
(handler / webhook_server) keeps working unchanged.
"""

import logging
from datetime import datetime, timezone

from app.repositories._sql import fetch_one, exec_write, insert_row, scalar

logger = logging.getLogger(__name__)

# The appointment "schema" — kept as a stable contract for the appointment module.
COLUMNS = [
    "appointment_id",
    "security_token",
    "patient_name",
    "patient_age",
    "patient_phone",
    "telegram_chat_id",
    "mother_id",
    "preferred_language",
    "preferred_date",
    "preferred_time",
    "symptoms",
    "status",
    "confirmed_date",
    "confirmed_time",
    "doctor_notes",
    "created_at",
    "updated_at",
]


def _ensure_workbook_exists():
    """No-op retained for back-compat (storage is now Postgres, not Excel)."""
    return None


def write_appointment(appointment: dict) -> None:
    """Insert a new appointment row."""
    row = {col: appointment.get(col, "") for col in COLUMNS}
    if not row.get("mother_id"):
        row.pop("mother_id", None)  # uuid column — never insert an empty string
    insert_row("appointments", row, known_cols=set(COLUMNS), uuid_cols={"mother_id"})
    logger.info(f"[Appointment] Written: {appointment.get('appointment_id')}")


def get_appointment_by_id(appointment_id: str) -> dict | None:
    """Fetch an appointment by its business id. Returns a dict (COLUMNS) or None."""
    row = fetch_one(
        "select * from appointments where appointment_id = :aid", {"aid": appointment_id}
    )
    if not row:
        return None
    return {col: row.get(col) for col in COLUMNS}


def update_appointment_status(
    appointment_id: str,
    security_token: str,
    new_status: str,
    confirmed_date: str = "",
    confirmed_time: str = "",
    doctor_notes: str = "",
) -> dict | None:
    """Update status after security_token validation. Returns the updated row or None."""
    existing = fetch_one(
        "select * from appointments where appointment_id = :aid", {"aid": appointment_id}
    )
    if not existing:
        logger.warning(f"[Appointment] Not found: {appointment_id}")
        return None

    if existing.get("security_token") != security_token:
        logger.warning(f"[Appointment] Token mismatch for {appointment_id}")
        return None

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    exec_write(
        "update appointments set status = :status, confirmed_date = :cd, "
        "confirmed_time = :ct, doctor_notes = :dn, updated_at = :updated "
        "where appointment_id = :aid",
        {
            "status": new_status,
            "cd": confirmed_date,
            "ct": confirmed_time,
            "dn": doctor_notes,
            "updated": now,
            "aid": appointment_id,
        },
    )
    logger.info(f"[Appointment] {appointment_id} → {new_status}")
    return get_appointment_by_id(appointment_id)


def is_slot_taken(preferred_date: str, preferred_time: str) -> bool:
    """Return True if a Pending/Confirmed appointment already occupies the slot."""
    count = scalar(
        "select count(*) from appointments where preferred_date = :d "
        "and preferred_time = :t and status in ('Pending', 'Confirmed')",
        {"d": preferred_date, "t": preferred_time},
    )
    return (count or 0) > 0
