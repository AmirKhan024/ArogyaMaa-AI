"""
Assessment Repository

Data access layer for the 'assessments' table (Postgres).
SINGLE SOURCE OF TRUTH for all health assessments. Function names, signatures, and
return shapes preserved from the MongoDB version.
"""

from sqlalchemy.exc import IntegrityError

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, update_by_id, scalar, utcnow,
)

_KNOWN = {
    "mother_id", "asha_id", "vitals", "symptoms", "asha_notes",
    "gestational_age_at_assessment", "assessment_number", "ai_evaluation",
    "alerts_sent", "documents_uploaded", "reviewed_by_doctor", "consultation_id",
    "doctor_reviewed_at", "client_uuid", "timestamp",
}
_JSONB = {"vitals", "symptoms", "ai_evaluation", "alerts_sent", "documents_uploaded"}
_UUID = {"mother_id", "asha_id", "consultation_id"}


def _limit_clause(limit):
    return (" limit :lim", {"lim": int(limit)}) if limit else ("", {})


def create(assessment_data):
    """
    Create a new assessment. Returns the new id (str).

    Idempotent on ``client_uuid`` (for offline replay): if an assessment with the same
    client_uuid already exists, its id is returned instead of creating a duplicate.
    """
    assessment_data = dict(assessment_data)

    # Offline replays carry a client-generated ``client_uuid``. Short-circuit if we have
    # already ingested it so a flaky-network retry never creates a duplicate row.
    client_uuid = assessment_data.get("client_uuid")
    if client_uuid:
        existing = _find_by_client_uuid(client_uuid)
        if existing:
            return existing
    else:
        # Never write an empty string into the unique column (would collide across rows).
        assessment_data.pop("client_uuid", None)

    assessment_data.setdefault("timestamp", utcnow())
    assessment_data.setdefault("symptoms", [])
    assessment_data.setdefault("documents_uploaded", [])
    assessment_data.setdefault("ai_evaluation", None)
    assessment_data.setdefault("alerts_sent", [])
    assessment_data.setdefault("consultation_id", None)
    assessment_data.setdefault("reviewed_by_doctor", False)
    assessment_data.setdefault("doctor_reviewed_at", None)

    # Per-mother assessment number = current count + 1
    count = scalar(
        "select count(*) from assessments where mother_id = cast(:mid as uuid)",
        {"mid": str(assessment_data["mother_id"])},
    )
    assessment_data["assessment_number"] = (count or 0) + 1

    try:
        return insert_row(
            "assessments", assessment_data,
            known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID,
        )
    except IntegrityError:
        # Race: a concurrent replay of the same client_uuid inserted first and tripped the
        # unique constraint. Treat it as idempotent success and return the winning row.
        if client_uuid:
            existing = _find_by_client_uuid(client_uuid)
            if existing:
                return existing
        raise


def _find_by_client_uuid(client_uuid):
    """Return the id (str) of an assessment with this client_uuid, or None."""
    row = fetch_one(
        "select id from assessments where client_uuid = :cu", {"cu": client_uuid}
    )
    return str(row["id"]) if row else None


def get_by_id(assessment_id):
    return fetch_one("select * from assessments where id = cast(:id as uuid)", {"id": str(assessment_id)})


def list_by_mother(mother_id, limit=None):
    lc, lp = _limit_clause(limit)
    return fetch_all(
        "select * from assessments where mother_id = cast(:mid as uuid) "
        "order by timestamp desc" + lc,
        {"mid": str(mother_id), **lp},
    )


def list_by_asha(asha_id, limit=None):
    lc, lp = _limit_clause(limit)
    return fetch_all(
        "select * from assessments where asha_id = cast(:aid as uuid) "
        "order by timestamp desc" + lc,
        {"aid": str(asha_id), **lp},
    )


def list_all(limit=None):
    lc, lp = _limit_clause(limit)
    return fetch_all("select * from assessments order by timestamp desc" + lc, lp)


def list_by_risk_category(risk_category, limit=None):
    lc, lp = _limit_clause(limit)
    return fetch_all(
        "select * from assessments where ai_evaluation->>'risk_category' = :rc "
        "order by timestamp desc" + lc,
        {"rc": (risk_category or "").upper(), **lp},
    )


def list_pending_doctor_review(doctor_id=None, limit=None):
    lc, lp = _limit_clause(limit)
    if doctor_id:
        return fetch_all(
            "select * from assessments where reviewed_by_doctor = false "
            "and mother_id in (select id from mothers where assigned_doctor_id = cast(:did as uuid)) "
            "order by timestamp desc" + lc,
            {"did": str(doctor_id), **lp},
        )
    return fetch_all(
        "select * from assessments where reviewed_by_doctor = false order by timestamp desc" + lc,
        lp,
    )


def get_latest_for_mother(mother_id):
    return fetch_one(
        "select * from assessments where mother_id = cast(:mid as uuid) "
        "order by timestamp desc limit 1",
        {"mid": str(mother_id)},
    )


def update_ai_evaluation(assessment_id, ai_evaluation_data):
    ai_evaluation_data = dict(ai_evaluation_data)
    ai_evaluation_data["evaluated_at"] = utcnow().isoformat()
    return update_by_id(
        "assessments", assessment_id, {"ai_evaluation": ai_evaluation_data},
        known_cols=_KNOWN, jsonb_cols=_JSONB,
    )


def add_alert(assessment_id, alert_data):
    """Append an alert to alerts_sent (JSONB array, read-modify-write)."""
    row = get_by_id(assessment_id)
    if not row:
        return False
    alert_data = dict(alert_data)
    alert_data["sent_at"] = utcnow().isoformat()
    alerts = list(row.get("alerts_sent") or [])
    alerts.append(alert_data)
    return update_by_id(
        "assessments", assessment_id, {"alerts_sent": alerts},
        known_cols=_KNOWN, jsonb_cols=_JSONB,
    )


def mark_as_reviewed(assessment_id, consultation_id, doctor_id):
    return update_by_id(
        "assessments", assessment_id,
        {
            "consultation_id": str(consultation_id),
            "reviewed_by_doctor": True,
            "doctor_reviewed_at": utcnow(),
        },
        known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID,
    )


def get_history_for_ai(mother_id, limit=5):
    return list_by_mother(mother_id, limit=limit)
