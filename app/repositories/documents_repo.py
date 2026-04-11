"""
Document Repository

Data access layer for the 'documents' collection.
Stores metadata for medical documents (lab reports, scans, prescriptions).
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(document_data):
    """
    Create a new document record.
    
    Args:
        document_data: Dictionary containing document information
            Required fields:
                - mother_id: ObjectId
                - uploaded_by: str ('mother', 'asha', 'doctor')
                - document_type: str
                - file_metadata: dict
            Optional fields:
                - uploaded_by_id: ObjectId
                - telegram_file_id: str
                - extracted_text: str
                - ai_analysis: dict
                - linked_to_assessment: ObjectId
                - visible_to: list
    
    Returns:
        ObjectId of the created document
    """
    documents = get_collection('documents')
    
    # Set default values
    document_data.setdefault('uploaded_at', datetime.utcnow())
    document_data.setdefault('extracted_text', None)
    document_data.setdefault('ai_analysis', None)
    document_data.setdefault('linked_to_assessment', None)
    document_data.setdefault('visible_to', ['mother', 'asha', 'doctor', 'admin'])
    
    result = documents.insert_one(document_data)
    return result.inserted_id


def get_by_id(document_id):
    """
    Get a document by ObjectId.
    
    Args:
        document_id: ObjectId or string representation
    
    Returns:
        Document or None if not found
    """
    documents = get_collection('documents')
    
    if isinstance(document_id, str):
        document_id = ObjectId(document_id)
    
    return documents.find_one({'_id': document_id})


def list_by_mother(mother_id, limit=None):
    """
    List all documents for a specific mother.
    
    Args:
        mother_id: ObjectId or string representation
        limit: Maximum number of documents to return (optional)
    
    Returns:
        List of document records
    """
    documents = get_collection('documents')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    query = documents.find({'mother_id': mother_id}).sort('uploaded_at', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def list_by_assessment(assessment_id):
    """
    List all documents linked to a specific assessment.
    
    Args:
        assessment_id: ObjectId or string representation
    
    Returns:
        List of document records
    """
    documents = get_collection('documents')
    
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    
    return list(documents.find({'linked_to_assessment': assessment_id}).sort('uploaded_at', -1))


def list_by_type(document_type, mother_id=None):
    """
    List documents by type, optionally filtered by mother.
    
    Args:
        document_type: Document type ('lab_report', 'ultrasound', 'prescription', 'other')
        mother_id: Filter by specific mother (optional)
    
    Returns:
        List of document records
    """
    documents = get_collection('documents')
    
    query_filter = {'document_type': document_type}
    
    if mother_id:
        if isinstance(mother_id, str):
            mother_id = ObjectId(mother_id)
        query_filter['mother_id'] = mother_id
    
    return list(documents.find(query_filter).sort('uploaded_at', -1))


def update_ai_analysis(document_id, ai_analysis_data):
    """
    Update the AI analysis section of a document.
    
    Args:
        document_id: ObjectId or string representation
        ai_analysis_data: Dictionary containing AI analysis results
            Expected fields:
                - key_findings: list
                - abnormal_values: list
    
    Returns:
        True if updated, False if not found
    """
    documents = get_collection('documents')
    
    if isinstance(document_id, str):
        document_id = ObjectId(document_id)
    
    ai_analysis_data['analyzed_at'] = datetime.utcnow()
    
    result = documents.update_one(
        {'_id': document_id},
        {'$set': {'ai_analysis': ai_analysis_data}}
    )
    
    return result.modified_count > 0


def update_extracted_text(document_id, extracted_text):
    """
    Update the extracted text (OCR result) for a document.
    
    Args:
        document_id: ObjectId or string representation
        extracted_text: Text extracted from the document
    
    Returns:
        True if updated, False if not found
    """
    documents = get_collection('documents')
    
    if isinstance(document_id, str):
        document_id = ObjectId(document_id)
    
    result = documents.update_one(
        {'_id': document_id},
        {'$set': {'extracted_text': extracted_text}}
    )
    
    return result.modified_count > 0


def link_to_assessment(document_id, assessment_id):
    """
    Link a document to a specific assessment.
    
    Args:
        document_id: ObjectId or string representation
        assessment_id: ObjectId or string representation
    
    Returns:
        True if updated, False if not found
    """
    documents = get_collection('documents')
    
    if isinstance(document_id, str):
        document_id = ObjectId(document_id)
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    
    result = documents.update_one(
        {'_id': document_id},
        {'$set': {'linked_to_assessment': assessment_id}}
    )
    
    return result.modified_count > 0


def delete(document_id):
    """
    Delete a document record.
    
    Note: This only deletes the metadata. File deletion should be handled separately.
    
    Args:
        document_id: ObjectId or string representation
    
    Returns:
        True if deleted, False if not found
    """
    documents = get_collection('documents')
    
    if isinstance(document_id, str):
        document_id = ObjectId(document_id)
    
    result = documents.delete_one({'_id': document_id})
    
    return result.deleted_count > 0


def add_doctor_review(document_id, review_data):
    """
    Add or update doctor's review for a document.
    
    Args:
        document_id: ObjectId or string representation
        review_data: Dictionary containing:
            - reviewed_at: datetime
            - reviewed_by_doctor_id: ObjectId
            - doctor_name: str
            - notes: str
            - ai_overridden: bool
            - corrected_analysis: dict (optional, if AI was overridden)
            - notification_sent_to: list
    
    Returns:
        True if updated successfully
    """
    documents = get_collection('documents')
    
    if isinstance(document_id, str):
        document_id = ObjectId(document_id)
    
    result = documents.update_one(
        {'_id': document_id},
        {'$set': {'doctor_review': review_data}}
    )
    
    return result.modified_count > 0
