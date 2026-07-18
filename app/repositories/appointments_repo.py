"""
Appointments Repository

Data access for the 'appointments' table. The Telegram booking flow writes rows
via appointment/excel_manager.py (a legacy-named shim over this table); this repo
adds the list/act operations used by dashboards and the bot's "My appointments"
view.

Rows use the business key ``appointment_id`` (uuid string) rather than the PK for
external references, plus a ``security_token`` guarding the email-link actions.
Statuses: Pending | Confirmed | Rescheduled | Cancelled.
"""

from app.repositories._sql import fetch_all, fetch_one, exec_write, utcnow

STATUSES = ("Pending", "Confirmed", "Rescheduled", "Cancelled")


def list_all(status=None, limit=200):
    """All appointments, newest first, optionally filtered by status."""
    where = ""
    params = {"lim": int(limit)}
    if status:
        where = "where status = :status "
        params["status"] = status
    return fetch_all(
        f"select * from appointments {where}order by created_at desc limit :lim", params
    )


def list_by_chat_id(telegram_chat_id, limit=10):
    """A mother's appointments (by her Telegram chat id), newest first."""
    return fetch_all(
        "select * from appointments where telegram_chat_id = :cid "
        "order by created_at desc limit :lim",
        {"cid": str(telegram_chat_id), "lim": int(limit)},
    )


def get_by_appointment_id(appointment_id):
    """Fetch one appointment by its business id. Returns dict or None."""
    return fetch_one(
        "select * from appointments where appointment_id = :aid",
        {"aid": str(appointment_id)},
    )


def update_status(appointment_id, new_status, confirmed_date="", confirmed_time="",
                  doctor_notes="", security_token=None):
    """
    Update an appointment's status (+ confirmed slot / notes).

    When ``security_token`` is given (email-link path) it must match; dashboard
    callers are already authenticated and pass None. Returns the updated row or
    None when the appointment is missing / token mismatched.
    """
    existing = get_by_appointment_id(appointment_id)
    if not existing:
        return None
    if security_token is not None and existing.get("security_token") != security_token:
        return None

    now = utcnow().isoformat(timespec="seconds")
    exec_write(
        "update appointments set status = :status, confirmed_date = :cd, "
        "confirmed_time = :ct, doctor_notes = :dn, updated_at = :updated "
        "where appointment_id = :aid",
        {
            "status": new_status,
            "cd": confirmed_date or existing.get("confirmed_date") or "",
            "ct": confirmed_time or existing.get("confirmed_time") or "",
            "dn": doctor_notes or existing.get("doctor_notes") or "",
            "updated": now,
            "aid": str(appointment_id),
        },
    )
    return get_by_appointment_id(appointment_id)
