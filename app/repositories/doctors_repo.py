"""
Doctor Repository

Data access layer for the 'doctors' collection.
Handles all CRUD operations for doctor profiles.
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(doctor_data):
    """
    Create a new doctor profile.
    
    Args:
        doctor_data: Dictionary containing doctor information
            Required fields:
                - name: str
                - specialization: str
                - phone: str
            Optional fields:
                - qualification: str
                - hospital: str
                - assigned_mothers: list of ObjectId
                - availability: dict
                - performance_stats: dict
    
    Returns:
        ObjectId of the created doctor
    """
    doctors = get_collection('doctors')
    
    # Set default values
    doctor_data.setdefault('assigned_mothers', [])
    doctor_data.setdefault('performance_stats', {
        'total_consultations': 0,
        'high_risk_cases_handled': 0,
        'average_response_time_hours': 0.0
    })
    doctor_data.setdefault('joined_at', datetime.utcnow())
    doctor_data.setdefault('active', True)
    
    result = doctors.insert_one(doctor_data)
    return result.inserted_id


def get_by_id(doctor_id):
    """
    Get a doctor by ObjectId.
    
    Args:
        doctor_id: ObjectId or string representation
    
    Returns:
        Doctor document or None if not found
    """
    doctors = get_collection('doctors')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    
    return doctors.find_one({'_id': doctor_id})


# Alias for consistency
find_by_id = get_by_id


def get_by_phone(phone):
    """
    Get a doctor by phone number.
    
    Args:
        phone: Phone number (string)
    
    Returns:
        Doctor document or None if not found
    """
    doctors = get_collection('doctors')
    return doctors.find_one({'phone': phone})


def list_all_active():
    """
    List all active doctors.
    
    Returns:
        List of active doctor documents
    """
    doctors = get_collection('doctors')
    return list(doctors.find({'active': True}))


def list_all():
    """
    List all doctors (active and inactive).
    
    Returns:
        List of all doctor documents
    """
    doctors = get_collection('doctors')
    return list(doctors.find({}))


def list_by_specialization(specialization):
    """
    List all doctors with a specific specialization.
    
    Args:
        specialization: Specialization name (string)
    
    Returns:
        List of doctor documents
    """
    doctors = get_collection('doctors')
    return list(doctors.find({'specialization': specialization, 'active': True}))


def update(doctor_id, update_data):
    """
    Update a doctor's profile.
    
    Args:
        doctor_id: ObjectId or string representation
        update_data: Dictionary of fields to update
    
    Returns:
        True if updated, False if not found
    """
    doctors = get_collection('doctors')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    
    result = doctors.update_one(
        {'_id': doctor_id},
        {'$set': update_data}
    )
    
    return result.modified_count > 0


def add_mother_assignment(doctor_id, mother_id):
    """
    Add a mother to a doctor's assigned list.
    
    Args:
        doctor_id: ObjectId or string representation
        mother_id: ObjectId or string representation
    
    Returns:
        True if added, False if not found or already assigned
    """
    doctors = get_collection('doctors')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    result = doctors.update_one(
        {'_id': doctor_id},
        {'$addToSet': {'assigned_mothers': mother_id}}
    )
    
    return result.modified_count > 0


def remove_mother_assignment(doctor_id, mother_id):
    """
    Remove a mother from a doctor's assigned list.
    
    Args:
        doctor_id: ObjectId or string representation
        mother_id: ObjectId or string representation
    
    Returns:
        True if removed, False if not found
    """
    doctors = get_collection('doctors')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    result = doctors.update_one(
        {'_id': doctor_id},
        {'$pull': {'assigned_mothers': mother_id}}
    )
    
    return result.modified_count > 0


def increment_consultation_count(doctor_id, is_high_risk=False):
    """
    Increment consultation statistics for a doctor.
    
    Args:
        doctor_id: ObjectId or string representation
        is_high_risk: Whether this was a high-risk case (bool)
    
    Returns:
        True if updated, False if not found
    """
    doctors = get_collection('doctors')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    
    update_fields = {
        '$inc': {
            'performance_stats.total_consultations': 1
        }
    }
    
    if is_high_risk:
        update_fields['$inc']['performance_stats.high_risk_cases_handled'] = 1
    
    result = doctors.update_one(
        {'_id': doctor_id},
        update_fields
    )
    
    return result.modified_count > 0


def deactivate(doctor_id):
    """
    Deactivate a doctor.
    
    Args:
        doctor_id: ObjectId or string representation
    
    Returns:
        True if deactivated, False if not found
    """
    return update(doctor_id, {'active': False})
