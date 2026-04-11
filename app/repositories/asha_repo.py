"""
ASHA Worker Repository

Data access layer for the 'asha_workers' collection.
Handles all CRUD operations for ASHA worker profiles.
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(asha_data):
    """
    Create a new ASHA worker profile.
    
    Args:
        asha_data: Dictionary containing ASHA information
            Required fields:
                - name: str
                - phone: str
                - area: str
            Optional fields:
                - district: str
                - state: str
                - assigned_mothers: list of ObjectId
                - performance_stats: dict
    
    Returns:
        ObjectId of the created ASHA worker
    """
    asha_workers = get_collection('asha_workers')
    
    # Set default values
    asha_data.setdefault('assigned_mothers', [])
    asha_data.setdefault('performance_stats', {
        'total_assessments': 0,
        'high_risk_detected': 0,
        'moderate_risk_detected': 0,
        'low_risk_detected': 0,
        'average_assessments_per_week': 0.0,
        'last_assessment_date': None
    })
    asha_data.setdefault('joined_at', datetime.utcnow())
    asha_data.setdefault('active', True)
    
    result = asha_workers.insert_one(asha_data)
    return result.inserted_id


def get_by_id(asha_id):
    """
    Get an ASHA worker by ObjectId.
    
    Args:
        asha_id: ObjectId or string representation
    
    Returns:
        ASHA worker document or None if not found
    """
    asha_workers = get_collection('asha_workers')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    
    return asha_workers.find_one({'_id': asha_id})


# Alias for consistency
find_by_id = get_by_id


def get_by_phone(phone):
    """
    Get an ASHA worker by phone number.
    
    Args:
        phone: Phone number (string)
    
    Returns:
        ASHA worker document or None if not found
    """
    asha_workers = get_collection('asha_workers')
    return asha_workers.find_one({'phone': phone})


def list_all_active():
    """
    List all active ASHA workers.
    
    Returns:
        List of active ASHA worker documents
    """
    asha_workers = get_collection('asha_workers')
    return list(asha_workers.find({'active': True}))


def list_all():
    """
    List all ASHA workers (active and inactive).
    
    Returns:
        List of all ASHA worker documents
    """
    asha_workers = get_collection('asha_workers')
    return list(asha_workers.find({}))


def list_by_area(area):
    """
    List all ASHA workers in a specific area.
    
    Args:
        area: Area name (string)
    
    Returns:
        List of ASHA worker documents
    """
    asha_workers = get_collection('asha_workers')
    return list(asha_workers.find({'area': area, 'active': True}))


def update(asha_id, update_data):
    """
    Update an ASHA worker's profile.
    
    Args:
        asha_id: ObjectId or string representation
        update_data: Dictionary of fields to update
    
    Returns:
        True if updated, False if not found
    """
    asha_workers = get_collection('asha_workers')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    
    result = asha_workers.update_one(
        {'_id': asha_id},
        {'$set': update_data}
    )
    
    return result.modified_count > 0


def add_mother_assignment(asha_id, mother_id):
    """
    Add a mother to an ASHA worker's assigned list.
    
    Args:
        asha_id: ObjectId or string representation
        mother_id: ObjectId or string representation
    
    Returns:
        True if added, False if not found or already assigned
    """
    asha_workers = get_collection('asha_workers')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    result = asha_workers.update_one(
        {'_id': asha_id},
        {'$addToSet': {'assigned_mothers': mother_id}}
    )
    
    return result.modified_count > 0


def remove_mother_assignment(asha_id, mother_id):
    """
    Remove a mother from an ASHA worker's assigned list.
    
    Args:
        asha_id: ObjectId or string representation
        mother_id: ObjectId or string representation
    
    Returns:
        True if removed, False if not found
    """
    asha_workers = get_collection('asha_workers')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    result = asha_workers.update_one(
        {'_id': asha_id},
        {'$pull': {'assigned_mothers': mother_id}}
    )
    
    return result.modified_count > 0


def increment_assessment_count(asha_id, risk_category):
    """
    Increment assessment statistics for an ASHA worker.
    
    Args:
        asha_id: ObjectId or string representation
        risk_category: 'LOW', 'MODERATE', or 'HIGH'
    
    Returns:
        True if updated, False if not found
    """
    asha_workers = get_collection('asha_workers')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    
    # Map risk category to field name
    risk_field_map = {
        'LOW': 'performance_stats.low_risk_detected',
        'MODERATE': 'performance_stats.moderate_risk_detected',
        'HIGH': 'performance_stats.high_risk_detected'
    }
    
    risk_field = risk_field_map.get(risk_category.upper())
    if not risk_field:
        return False
    
    result = asha_workers.update_one(
        {'_id': asha_id},
        {
            '$inc': {
                'performance_stats.total_assessments': 1,
                risk_field: 1
            },
            '$set': {
                'performance_stats.last_assessment_date': datetime.utcnow()
            }
        }
    )
    
    return result.modified_count > 0


def deactivate(asha_id):
    """
    Deactivate an ASHA worker.
    
    Args:
        asha_id: ObjectId or string representation
    
    Returns:
        True if deactivated, False if not found
    """
    return update(asha_id, {'active': False})
