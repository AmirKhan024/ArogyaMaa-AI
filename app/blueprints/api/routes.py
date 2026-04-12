"""
API Routes for Document Management

General API endpoints accessible to all user types (ASHA, Doctor, Mother).
"""

from flask import Blueprint, jsonify, current_app
from bson import ObjectId
from app.repositories import documents_repo, mothers_repo

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/documents/<document_id>', methods=['GET'])
def get_document_details(document_id):
    """
    Get full details of a document including AI analysis.
    
    Args:
        document_id: Document ObjectId
    
    Returns:
        Full document with all metadata and AI analysis
    """
    try:
        # Get document
        document = documents_repo.get_by_id(document_id)
        
        if not document:
            return jsonify({"error": "Document not found"}), 404
        
        # Get mother info
        mother = mothers_repo.get_by_id(document['mother_id'])
        
        # Get ASHA worker info if uploaded by ASHA
        uploaded_by_name = None
        if document.get('uploaded_by') == 'asha' and document.get('uploaded_by_id'):
            from app.repositories import asha_repo
            asha_worker = asha_repo.get_by_id(document.get('uploaded_by_id'))
            if asha_worker:
                uploaded_by_name = asha_worker.get('name', 'Unknown ASHA')
        elif document.get('uploaded_by') == 'mother':
            uploaded_by_name = mother.get('name') if mother else 'Unknown Mother'
        
        # Clean doctor_review to remove ObjectId fields
        doctor_review = document.get('doctor_review')
        if doctor_review:
            doctor_review_clean = {
                'reviewed_at': doctor_review.get('reviewed_at').isoformat() if doctor_review.get('reviewed_at') else None,
                'doctor_name': doctor_review.get('doctor_name'),
                'notes': doctor_review.get('notes'),
                'ai_overridden': doctor_review.get('ai_overridden', False),
                'corrected_analysis': doctor_review.get('corrected_analysis'),
                'notification_sent_to': doctor_review.get('notification_sent_to', [])
            }
        else:
            doctor_review_clean = None
        
        # Format response
        response = {
            "document_id": str(document['_id']),
            "mother_id": str(document['mother_id']),
            "mother_name": mother.get('name') if mother else 'Unknown',
            "document_type": document.get('document_type'),
            "description": document.get('description', ''),
            "uploaded_at": document.get('uploaded_at').isoformat() if document.get('uploaded_at') else None,
            "uploaded_by": document.get('uploaded_by'),
            "uploaded_by_name": uploaded_by_name or document.get('uploaded_by_name'),
            "file_metadata": document.get('file_metadata', {}),
            "extracted_text": document.get('extracted_text'),
            "ai_analysis": document.get('ai_analysis'),
            "doctor_review": doctor_review_clean
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching document details: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch document details",
            "details": str(e)
        }), 500


@api_bp.route('/health', methods=['GET'])
def health():
    """API health check"""
    return jsonify({
        "service": "api",
        "status": "active"
    }), 200


@api_bp.route('/documents/file/<filename>', methods=['GET'])
def get_document_file(filename):
    """
    Serve uploaded document files.
    
    Args:
        filename: Stored filename of the document
    """
    import os
    from flask import send_from_directory
    try:
        upload_dir = os.path.join(current_app.root_path, '..', 'uploads', 'documents')
        return send_from_directory(upload_dir, filename)
    except Exception as e:
        current_app.logger.error(f"Error serving document file: {e}", exc_info=True)
        return jsonify({"error": "File not found"}), 404
