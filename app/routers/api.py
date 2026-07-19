"""
API Router — FastAPI port of app/blueprints/api/routes.py.

General API endpoints accessible to all user types (ASHA, Doctor, Mother).
"""

import logging
import os

from fastapi import APIRouter
from starlette.responses import FileResponse

from app.repositories import documents_repo, mothers_repo
from app.routers._utils import json_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_UPLOAD_DIR = os.path.realpath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "uploads", "documents")
)


def _iso(val):
    """Return an ISO string whether val is a datetime or already a string."""
    if val is None:
        return None
    return val.isoformat() if hasattr(val, 'isoformat') else str(val)


@router.get("/documents/file/{filename}", name="api.get_document_file")
def get_document_file(filename: str):
    """Serve uploaded document files."""
    try:
        full = os.path.realpath(os.path.join(_UPLOAD_DIR, filename))
        if not full.startswith(_UPLOAD_DIR + os.sep) or not os.path.isfile(full):
            return json_response({"error": "File not found"}, 404)
        return FileResponse(full)
    except Exception as e:
        logger.error(f"Error serving document file: {e}", exc_info=True)
        return json_response({"error": "File not found"}, 404)


@router.get("/documents/{document_id}", name="api.get_document_details")
def get_document_details(document_id: str):
    """Get full details of a document including AI analysis."""
    try:
        document = documents_repo.get_by_id(document_id)

        if not document:
            return json_response({"error": "Document not found"}, 404)

        mother = mothers_repo.get_by_id(document['mother_id'])

        uploaded_by_name = None
        if document.get('uploaded_by') == 'asha' and document.get('uploaded_by_id'):
            from app.repositories import asha_repo
            asha_worker = asha_repo.get_by_id(document.get('uploaded_by_id'))
            if asha_worker:
                uploaded_by_name = asha_worker.get('name', 'Unknown ASHA')
        elif document.get('uploaded_by') == 'mother':
            uploaded_by_name = mother.get('name') if mother else 'Unknown Mother'

        doctor_review = document.get('doctor_review')
        if doctor_review:
            doctor_review_clean = {
                'reviewed_at': _iso(doctor_review.get('reviewed_at')),
                'doctor_name': doctor_review.get('doctor_name'),
                'notes': doctor_review.get('notes'),
                'ai_overridden': doctor_review.get('ai_overridden', False),
                'corrected_analysis': doctor_review.get('corrected_analysis'),
                'notification_sent_to': doctor_review.get('notification_sent_to', [])
            }
        else:
            doctor_review_clean = None

        response = {
            "document_id": str(document['_id']),
            "mother_id": str(document['mother_id']),
            "mother_name": mother.get('name') if mother else 'Unknown',
            "document_type": document.get('document_type'),
            "description": document.get('description', ''),
            "uploaded_at": _iso(document.get('uploaded_at')),
            "uploaded_by": document.get('uploaded_by'),
            "uploaded_by_name": uploaded_by_name or document.get('uploaded_by_name'),
            "file_metadata": document.get('file_metadata', {}),
            "extracted_text": document.get('extracted_text'),
            "ai_analysis": document.get('ai_analysis'),
            "doctor_review": doctor_review_clean
        }

        return json_response(response, 200)

    except Exception as e:
        logger.error(f"Error fetching document details: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch document details",
            "details": str(e)
        }, 500)


@router.get("/health", name="api.health")
def health():
    """API health check"""
    return json_response({
        "service": "api",
        "status": "active"
    }, 200)
