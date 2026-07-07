"""
Consultation Repository

Data access layer for the 'consultations' table (Postgres).
Stores the doctor's authoritative medical input for assessments.
"""

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, update_by_id, utcnow,
)

_KNOWN = {
    "assessment_id", "mother_id", "doctor_id", "diagnosis", "clinical_observations",
    "updated_vitals", "treatment_plan", "next_visit_date", "overrides_ai_assessment",
    "doctor_risk_assessment", "override_reason", "consultation_notes",
    "message_sent_to_mother", "message_sent_at", "consultation_date",
}
_JSONB = {"updated_vitals", "treatment_plan"}
_UUID = {"assessment_id", "mother_id", "doctor_id"}


def create(consultation_data):
    """Create a new consultation. Returns the new id (str)."""
    consultation_data.setdefault("consultation_date", utcnow())
    consultation_data.setdefault("overrides_ai_assessment", False)
    consultation_data.setdefault("message_sent_to_mother", None)
    consultation_data.setdefault("message_sent_at", None)
    return insert_row(
        "consultations", consultation_data,
        known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID,
    )


def get_by_id(consultation_id):
    return fetch_one(
        "select * from consultations where id = cast(:id as uuid)", {"id": str(consultation_id)}
    )


def get_by_assessment_id(assessment_id):
    return fetch_one(
        "select * from consultations where assessment_id = cast(:aid as uuid)",
        {"aid": str(assessment_id)},
    )


def list_by_mother(mother_id, limit=None):
    lc = " limit :lim" if limit else ""
    params = {"mid": str(mother_id)}
    if limit:
        params["lim"] = int(limit)
    return fetch_all(
        "select * from consultations where mother_id = cast(:mid as uuid) "
        "order by consultation_date desc" + lc,
        params,
    )


def list_by_doctor(doctor_id, limit=None):
    lc = " limit :lim" if limit else ""
    params = {"did": str(doctor_id)}
    if limit:
        params["lim"] = int(limit)
    return fetch_all(
        "select * from consultations where doctor_id = cast(:did as uuid) "
        "order by consultation_date desc" + lc,
        params,
    )


def get_latest_for_mother(mother_id):
    return fetch_one(
        "select * from consultations where mother_id = cast(:mid as uuid) "
        "order by consultation_date desc limit 1",
        {"mid": str(mother_id)},
    )


def list_upcoming_visits(doctor_id=None, days_ahead=7):
    where_doctor = " and doctor_id = cast(:did as uuid)" if doctor_id else ""
    params = {"days": int(days_ahead)}
    if doctor_id:
        params["did"] = str(doctor_id)
    return fetch_all(
        "select * from consultations where next_visit_date >= date_trunc('day', now()) "
        "and next_visit_date <= now() + (:days || ' days')::interval" + where_doctor +
        " order by next_visit_date asc",
        params,
    )


def update(consultation_id, update_data):
    return update_by_id(
        "consultations", consultation_id, update_data,
        known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID,
    )


def set_message_sent(consultation_id, message_text):
    return update(consultation_id, {
        "message_sent_to_mother": message_text,
        "message_sent_at": utcnow(),
    })
