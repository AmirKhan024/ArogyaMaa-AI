"""
Assessment Repository

Data access layer for the 'assessments' collection.
SINGLE SOURCE OF TRUTH for all health assessments.
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(assessment_data):
    """
    Create a new assessment record.
    
    Args:
        assessment_data: Dictionary containing assessment information
            Required fields:
                - mother_id: ObjectId
                - asha_id: ObjectId
                - vitals: dict
                - symptoms: list
            Optional fields:
                - asha_notes: str
                - gestational_age_at_assessment: int
                - documents_uploaded: list of ObjectId
    
    Returns:
        ObjectId of the created assessment
    """
    assessments = get_collection('assessments')
    
    # Set default values
    assessment_data.setdefault('timestamp', datetime.utcnow())
    assessment_data.setdefault('symptoms', [])
    assessment_data.setdefault('documents_uploaded', [])
    assessment_data.setdefault('ai_evaluation', None)
    assessment_data.setdefault('alerts_sent', [])
    assessment_data.setdefault('consultation_id', None)
    assessment_data.setdefault('reviewed_by_doctor', False)
    assessment_data.setdefault('doctor_reviewed_at', None)
    
    # Calculate assessment number for this mother
    mother_id = assessment_data['mother_id']
    assessment_count = assessments.count_documents({'mother_id': mother_id})
    assessment_data['assessment_number'] = assessment_count + 1
    
    result = assessments.insert_one(assessment_data)
    return result.inserted_id


def get_by_id(assessment_id):
    """
    Get an assessment by ObjectId.
    
    Args:
        assessment_id: ObjectId or string representation
    
    Returns:
        Assessment document or None if not found
    """
    assessments = get_collection('assessments')
    
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    
    return assessments.find_one({'_id': assessment_id})


def list_by_mother(mother_id, limit=None):
    """
    List all assessments for a specific mother, sorted by most recent first.
    
    Args:
        mother_id: ObjectId or string representation
        limit: Maximum number of assessments to return (optional)
    
    Returns:
        List of assessment documents
    """
    assessments = get_collection('assessments')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    query = assessments.find({'mother_id': mother_id}).sort('timestamp', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def list_by_asha(asha_id, limit=None):
    """
    List all assessments submitted by a specific ASHA worker.
    
    Args:
        asha_id: ObjectId or string representation
        limit: Maximum number of assessments to return (optional)
    
    Returns:
        List of assessment documents
    """
    assessments = get_collection('assessments')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    
    query = assessments.find({'asha_id': asha_id}).sort('timestamp', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def list_all(limit=None):
    """
    List all assessments in the system.
    
    Args:
        limit: Maximum number of assessments to return (optional)
    
    Returns:
        List of assessment documents sorted by most recent first
    """
    assessments = get_collection('assessments')
    
    query = assessments.find({}).sort('timestamp', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def list_by_risk_category(risk_category, limit=None):
    """
    List all assessments by risk category.
    
    Args:
        risk_category: 'LOW', 'MODERATE', or 'HIGH'
        limit: Maximum number of assessments to return (optional)
    
    Returns:
        List of assessment documents
    """
    assessments = get_collection('assessments')
    
    query = assessments.find({
        'ai_evaluation.risk_category': risk_category.upper()
    }).sort('timestamp', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def list_pending_doctor_review(doctor_id=None, limit=None):
    """
    List assessments pending doctor review.
    
    Args:
        doctor_id: Filter by specific doctor (optional)
        limit: Maximum number of assessments to return (optional)
    
    Returns:
        List of assessment documents
    """
    assessments = get_collection('assessments')
    mothers = get_collection('mothers')
    
    query_filter = {'reviewed_by_doctor': False}
    
    if doctor_id:
        if isinstance(doctor_id, str):
            doctor_id = ObjectId(doctor_id)
        
        # Find mothers assigned to this doctor
        mother_ids = [m['_id'] for m in mothers.find({'assigned_doctor_id': doctor_id})]
        query_filter['mother_id'] = {'$in': mother_ids}
    
    query = assessments.find(query_filter).sort('timestamp', -1)
    
    if limit:
        query = query.limit(limit)
    
    return list(query)


def get_latest_for_mother(mother_id):
    """
    Get the most recent assessment for a mother.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        Assessment document or None if not found
    """
    assessments = get_collection('assessments')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    return assessments.find_one(
        {'mother_id': mother_id},
        sort=[('timestamp', -1)]
    )


def update_ai_evaluation(assessment_id, ai_evaluation_data):
    """
    Update the AI evaluation section of an assessment.
    
    Args:
        assessment_id: ObjectId or string representation
        ai_evaluation_data: Dictionary containing AI evaluation results
            Expected fields:
                - risk_score: int (0-100)
                - risk_category: str ('LOW', 'MODERATE', 'HIGH')
                - reasoning: dict
                - recommendations: list
                - langsmith_trace_id: str
    
    Returns:
        True if updated, False if not found
    """
    assessments = get_collection('assessments')
    
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    
    ai_evaluation_data['evaluated_at'] = datetime.utcnow()
    
    result = assessments.update_one(
        {'_id': assessment_id},
        {'$set': {'ai_evaluation': ai_evaluation_data}}
    )
    
    return result.modified_count > 0


def add_alert(assessment_id, alert_data):
    """
    Add an alert to the alerts_sent array.
    
    Args:
        assessment_id: ObjectId or string representation
        alert_data: Dictionary containing alert information
            Expected fields:
                - recipient: str ('mother', 'asha', 'doctor')
                - recipient_id: ObjectId
                - message: str
                - delivery_status: str
    
    Returns:
        True if added, False if not found
    """
    assessments = get_collection('assessments')
    
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    
    alert_data['sent_at'] = datetime.utcnow()
    
    result = assessments.update_one(
        {'_id': assessment_id},
        {'$push': {'alerts_sent': alert_data}}
    )
    
    return result.modified_count > 0


def mark_as_reviewed(assessment_id, consultation_id, doctor_id):
    """
    Mark an assessment as reviewed by a doctor.
    
    Args:
        assessment_id: ObjectId or string representation
        consultation_id: ObjectId of the consultation document
        doctor_id: ObjectId of the reviewing doctor
    
    Returns:
        True if updated, False if not found
    """
    assessments = get_collection('assessments')
    
    if isinstance(assessment_id, str):
        assessment_id = ObjectId(assessment_id)
    if isinstance(consultation_id, str):
        consultation_id = ObjectId(consultation_id)
    
    result = assessments.update_one(
        {'_id': assessment_id},
        {
            '$set': {
                'consultation_id': consultation_id,
                'reviewed_by_doctor': True,
                'doctor_reviewed_at': datetime.utcnow()
            }
        }
    )
    
    return result.modified_count > 0


def get_history_for_ai(mother_id, limit=5):
    """
    Get recent assessment history for AI context (trend analysis).
    
    Args:
        mother_id: ObjectId or string representation
        limit: Number of recent assessments to retrieve (default: 5)
    
    Returns:
        List of assessment documents (most recent first)
    """
    return list_by_mother(mother_id, limit=limit)
