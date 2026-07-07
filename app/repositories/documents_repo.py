"""
Document Repository

Data access layer for the 'documents' table (Postgres).
Stores metadata for medical documents (lab reports, scans, prescriptions).
"""

from app.repositories._sql import (
    fetch_all, fetch_one, insert_row, update_by_id, exec_write, utcnow,
)

_KNOWN = {
    "mother_id", "uploaded_by", "uploaded_by_id", "document_type", "file_metadata",
    "telegram_file_id", "extracted_text", "ai_analysis", "linked_to_assessment",
    "visible_to", "doctor_review", "uploaded_at",
}
_JSONB = {"file_metadata", "ai_analysis", "visible_to", "doctor_review"}
_UUID = {"mother_id", "uploaded_by_id", "linked_to_assessment"}


def create(document_data):
    """Create a new document record. Returns the new id (str)."""
    document_data.setdefault("uploaded_at", utcnow())
    document_data.setdefault("extracted_text", None)
    document_data.setdefault("ai_analysis", None)
    document_data.setdefault("linked_to_assessment", None)
    document_data.setdefault("visible_to", ["mother", "asha", "doctor", "admin"])
    return insert_row(
        "documents", document_data,
        known_cols=_KNOWN, jsonb_cols=_JSONB, uuid_cols=_UUID,
    )


def get_by_id(document_id):
    return fetch_one("select * from documents where id = cast(:id as uuid)", {"id": str(document_id)})


def list_by_mother(mother_id, limit=None):
    lc = " limit :lim" if limit else ""
    params = {"mid": str(mother_id)}
    if limit:
        params["lim"] = int(limit)
    return fetch_all(
        "select * from documents where mother_id = cast(:mid as uuid) order by uploaded_at desc" + lc,
        params,
    )


def list_by_assessment(assessment_id):
    return fetch_all(
        "select * from documents where linked_to_assessment = cast(:aid as uuid) "
        "order by uploaded_at desc",
        {"aid": str(assessment_id)},
    )


def list_by_type(document_type, mother_id=None):
    if mother_id:
        return fetch_all(
            "select * from documents where document_type = :dt and mother_id = cast(:mid as uuid) "
            "order by uploaded_at desc",
            {"dt": document_type, "mid": str(mother_id)},
        )
    return fetch_all(
        "select * from documents where document_type = :dt order by uploaded_at desc",
        {"dt": document_type},
    )


def update_ai_analysis(document_id, ai_analysis_data):
    ai_analysis_data = dict(ai_analysis_data)
    ai_analysis_data["analyzed_at"] = utcnow().isoformat()
    return update_by_id(
        "documents", document_id, {"ai_analysis": ai_analysis_data},
        known_cols=_KNOWN, jsonb_cols=_JSONB,
    )


def update_extracted_text(document_id, extracted_text):
    return update_by_id("documents", document_id, {"extracted_text": extracted_text}, known_cols=_KNOWN)


def link_to_assessment(document_id, assessment_id):
    return update_by_id(
        "documents", document_id, {"linked_to_assessment": str(assessment_id)},
        known_cols=_KNOWN, uuid_cols=_UUID,
    )


def delete(document_id):
    return exec_write(
        "delete from documents where id = cast(:id as uuid)", {"id": str(document_id)}
    ) > 0


def add_doctor_review(document_id, review_data):
    return update_by_id(
        "documents", document_id, {"doctor_review": review_data},
        known_cols=_KNOWN, jsonb_cols=_JSONB,
    )
