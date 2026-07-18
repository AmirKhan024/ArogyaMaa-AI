"""
Messages Repository

The old MongoDB 'messages' collection held two distinct shapes, so it is split across
two Postgres tables:
  * message_threads  — per-mother chat history (embedded ``messages`` JSONB array)
  * notifications    — standalone alerts addressed to an ASHA worker or doctor

Public function names, signatures, and return shapes are preserved. Timestamps inside
the JSONB messages array are ISO strings (JSONB cannot hold native datetimes).
"""

import uuid

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, exec_write, utcnow,
)

# ── Standalone notifications ───────────────────────────────────────────────────

_NOTIF_KNOWN = {
    "mother_id", "mother_name", "telegram_chat_id", "to_asha_id", "to_doctor_id",
    "message_type", "content", "message", "subject", "read", "from_doctor",
    "doctor_name", "document_id", "timestamp",
    "is_alert", "alert_type", "related_assessment_id", "sender_name",
}
_NOTIF_UUID = {"mother_id", "to_asha_id", "to_doctor_id", "document_id", "related_assessment_id"}


def create(message_data):
    """Create a single standalone notification message. Returns the new id (str)."""
    message_data.setdefault("timestamp", utcnow())
    return insert_row(
        "notifications", message_data, known_cols=_NOTIF_KNOWN, uuid_cols=_NOTIF_UUID
    )


def list_by_recipient(recipient_id, recipient_type="asha", limit=None):
    """Get notifications sent to a specific ASHA worker or doctor (most recent first)."""
    col = {"asha": "to_asha_id", "doctor": "to_doctor_id"}.get(recipient_type)
    if not col:
        return []
    lc = " limit :lim" if limit else ""
    params = {"rid": str(recipient_id)}
    if limit:
        params["lim"] = int(limit)
    return fetch_all(
        f"select * from notifications where {col} = cast(:rid as uuid) "
        f"order by timestamp desc" + lc,
        params,
    )


def list_notifications_for_mother(mother_id, limit=None, exclude_from_mother=False):
    """List notifications addressed to / about a mother (most recent first)."""
    where = "mother_id = cast(:mid as uuid)"
    if exclude_from_mother:
        where += " and (message_type is distinct from 'from_mother')"
    lc = " limit :lim" if limit else ""
    params = {"mid": str(mother_id)}
    if limit:
        params["lim"] = int(limit)
    return fetch_all(
        f"select * from notifications where {where} order by timestamp desc" + lc, params
    )


def mark_notification_read(notification_id):
    """Mark a single notification as read. Returns True if a row changed."""
    return exec_write(
        "update notifications set read = true where id = cast(:id as uuid)",
        {"id": str(notification_id)},
    ) > 0


def backfill_routing_for_mother(mother_id, asha_id=None, doctor_id=None):
    """
    Attach a newly assigned care team to this mother's previously unrouted
    'from_mother' notifications so earlier messages appear in their dashboards.
    Returns the number of rows updated.
    """
    sets, params = [], {"mid": str(mother_id)}
    if asha_id:
        sets.append("to_asha_id = coalesce(to_asha_id, cast(:aid as uuid))")
        params["aid"] = str(asha_id)
    if doctor_id:
        sets.append("to_doctor_id = coalesce(to_doctor_id, cast(:did as uuid))")
        params["did"] = str(doctor_id)
    if not sets:
        return 0
    return exec_write(
        f"update notifications set {', '.join(sets)} "
        "where mother_id = cast(:mid as uuid) and message_type = 'from_mother' "
        "and (to_asha_id is null or to_doctor_id is null)",
        params,
    )


def mark_all_notifications_read(asha_id):
    """Mark all of an ASHA worker's notifications as read. Returns count updated."""
    return exec_write(
        "update notifications set read = true "
        "where to_asha_id = cast(:aid as uuid) and read is not true",
        {"aid": str(asha_id)},
    )


# ── Per-mother message threads ─────────────────────────────────────────────────

def create_thread(mother_id):
    """Create a new (empty) message thread for a mother. Returns the new id (str)."""
    return insert_row(
        "message_threads",
        {
            "mother_id": str(mother_id),
            "messages": [],
            "created_at": utcnow(),
            "last_message_at": utcnow(),
            "total_messages": 0,
        },
        known_cols={"mother_id", "messages", "created_at", "last_message_at", "total_messages"},
        jsonb_cols={"messages"},
        uuid_cols={"mother_id"},
    )


def get_by_mother_id(mother_id):
    return fetch_one(
        "select * from message_threads where mother_id = cast(:mid as uuid)",
        {"mid": str(mother_id)},
    )


def _save_messages(mother_id, messages, *, bump_last=False, total=None):
    sets = ["messages = cast(:msgs as jsonb)"]
    params = {"mid": str(mother_id), "msgs": None}
    from app.db import to_jsonb
    params["msgs"] = to_jsonb(messages)
    if bump_last:
        sets.append("last_message_at = now()")
    if total is not None:
        sets.append("total_messages = :total")
        params["total"] = int(total)
    sql = f"update message_threads set {', '.join(sets)} where mother_id = cast(:mid as uuid)"
    return exec_write(sql, params) > 0


def add_message(mother_id, message_data):
    """
    Append a message to a mother's chat thread. Auto-creates the thread if missing
    (so messages are never silently dropped). Returns True on success.
    """
    thread = get_by_mother_id(mother_id)
    if not thread:
        create_thread(mother_id)
        thread = get_by_mother_id(mother_id)
        if not thread:
            return False

    message_data = dict(message_data)
    message_data["message_id"] = f"msg_{uuid.uuid4().hex[:8]}"
    message_data["timestamp"] = utcnow().isoformat()
    message_data.setdefault("read_by_mother", False)
    message_data.setdefault("read_at", None)
    # Ensure any id fields are JSON-serializable strings
    if message_data.get("sender_id") is not None:
        message_data["sender_id"] = str(message_data["sender_id"])

    messages = list(thread.get("messages") or [])
    messages.append(message_data)
    return _save_messages(
        mother_id, messages, bump_last=True, total=(thread.get("total_messages") or 0) + 1
    )


def get_messages(mother_id, limit=None, skip=0):
    """Return messages (newest first), honoring skip/limit."""
    thread = get_by_mother_id(mother_id)
    if not thread:
        return []
    messages = list(reversed(thread.get("messages") or []))
    if skip:
        messages = messages[skip:]
    if limit:
        messages = messages[:limit]
    return messages


def get_by_mother(mother_id, sender_type=None, limit=None):
    messages = get_messages(mother_id)
    if sender_type:
        messages = [m for m in messages if m.get("sender_type") == sender_type]
    if limit:
        messages = messages[:limit]
    return messages


def mark_as_read(mother_id, message_id):
    thread = get_by_mother_id(mother_id)
    if not thread:
        return False
    messages = list(thread.get("messages") or [])
    changed = False
    for m in messages:
        if m.get("message_id") == message_id:
            m["read_by_mother"] = True
            m["read_at"] = utcnow().isoformat()
            changed = True
    if not changed:
        return False
    return _save_messages(mother_id, messages)


def mark_all_as_read(mother_id):
    thread = get_by_mother_id(mother_id)
    if not thread:
        return False
    messages = list(thread.get("messages") or [])
    for m in messages:
        if not m.get("read_by_mother", False):
            m["read_by_mother"] = True
            m["read_at"] = utcnow().isoformat()
    return _save_messages(mother_id, messages)


def get_unread_count(mother_id):
    thread = get_by_mother_id(mother_id)
    if not thread:
        return 0
    return sum(
        1 for m in (thread.get("messages") or [])
        if not m.get("read_by_mother", False) and m.get("sender_type") != "mother"
    )


def get_recent_threads(limit=10):
    return fetch_all(
        "select * from message_threads order by last_message_at desc limit :lim",
        {"lim": int(limit)},
    )


def delete_thread(mother_id):
    return exec_write(
        "delete from message_threads where mother_id = cast(:mid as uuid)",
        {"mid": str(mother_id)},
    ) > 0
