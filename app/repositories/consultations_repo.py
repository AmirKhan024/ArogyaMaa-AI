"""
Consultation Repository

Data access layer for the 'consultations' collection.
Stores doctor's authoritative medical input for assessments.
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(consultation_data):
    """
    Create a new consultation record.
    
    Args:
        consultation_data: Dictionary containing consultation information
            Required fields:
                - assessment_id: ObjectId
                - mother_id: ObjectId
                - doctor_id: ObjectId
                - diagnosis: str
            Optional fields:
                - clinical_observations: str
                - updated_vitals: dict
                - treatment_plan: dict
                - next_visit_date: datetime
                - overrides_ai_assessment: bool
                - doctor_risk_assessment: str
                - override_reason: str
                - consultation_notes: str
    
    Returns:
        ObjectId of the created consultation
    """
    consultations = get_collection('consultations')
    
    # Set default values
    consultation_data.setdefault('consultation_date', datetime.utcnow())
    consultation_data.setdefault('overrides_ai_assessment', False)
    consultation_data.setdefault('message_sent_to_mother', None)
    consultation_data.setdefault('message_sent_at', None)
    
    result = consultations.insert_one(consultation_data)
    return result.inserted_id


def get_by_id(consultation_id):
    """
    Get a consultation by ObjectId.
    
    Args:
        consultation_id: ObjectId or string representation
    
    Returns:
        Consultation document or None if not found
    """
    consultations = get_collection('consultations')
    
    if isinstance(consultation_id, str):
        consultation_id = ObjectId(consultation_id)
    
    return consultations.find_one({'_id': consultation_id})


def get_by_assessment_id(assessment_id):
    """
    Get consultation for a specific assessment.
    
    Args:
        assessment_id: ObjectId or string representation
    
    Returns:
        Consultation document or None if not found
    """
    consultations = get_collection('consultations')
    
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    
    return consultations.find_one({'assessment_id': assessment_id})


def list_by_mother(mother_id, limit=None):
    """
    List all consultations for a specific mother.
    
    Args:
        mother_id: ObjectId or string representation
        limit: Maximum number of consultations to return (optional)
    
    Returns:
        List of consultation documents
    """
    consultations = get_collection('consultations')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    query = consultations.find({'mother_id': mother_id}).sort('consultation_date', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def list_by_doctor(doctor_id, limit=None):
    """
    List all consultations by a specific doctor.
    
    Args:
        doctor_id: ObjectId or string representation
        limit: Maximum number of consultations to return (optional)
    
    Returns:
        List of consultation documents
    """
    consultations = get_collection('consultations')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    
    query = consultations.find({'doctor_id': doctor_id}).sort('consultation_date', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def get_latest_for_mother(mother_id):
    """
    Get the most recent consultation for a mother.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        Consultation document or None if not found
    """
    consultations = get_collection('consultations')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    return consultations.find_one(
        {'mother_id': mother_id},
        sort=[('consultation_date', -1)]
    )


def list_upcoming_visits(doctor_id=None, days_ahead=7):
    """
    List consultations with upcoming follow-up visits.
    
    Args:
        doctor_id: Filter by specific doctor (optional)
        days_ahead: Number of days to look ahead (default: 7)
    
    Returns:
        List of consultation documents with upcoming visits
    """
    consultations = get_collection('consultations')
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    future_date = datetime.utcnow().replace(hour=23, minute=59, second=59) + timedelta(days=days_ahead)
    
    query_filter = {
        'next_visit_date': {
            '$gte': today,
            '$lte': future_date
        }
    }
    
    if doctor_id:
        if isinstance(doctor_id, str):
            doctor_id = ObjectId(doctor_id)
        query_filter['doctor_id'] = doctor_id
    
    return list(consultations.find(query_filter).sort('next_visit_date', 1))


def update(consultation_id, update_data):
    """
    Update a consultation record.
    
    Args:
        consultation_id: ObjectId or string representation
        update_data: Dictionary of fields to update
    
    Returns:
        True if updated, False if not found
    """
    consultations = get_collection('consultations')
    
    if isinstance(consultation_id, str):
        consultation_id = ObjectId(consultation_id)
    
    result = consultations.update_one(
        {'_id': consultation_id},
        {'$set': update_data}
    )
    
    return result.modified_count > 0


def set_message_sent(consultation_id, message_text):
    """
    Record that a message was sent to the mother for this consultation.
    
    Args:
        consultation_id: ObjectId or string representation
        message_text: The message sent to the mother
    
    Returns:
        True if updated, False if not found
    """
    return update(consultation_id, {
        'message_sent_to_mother': message_text,
        'message_sent_at': datetime.utcnow()
    })


# Need timedelta for upcoming visits
from datetime import timedelta
