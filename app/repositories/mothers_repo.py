"""
Mother Repository

Data access layer for the 'mothers' collection.
Handles all CRUD operations for mother profiles.
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(mother_data):
    """
    Create a new mother profile.
    
    Args:
        mother_data: Dictionary containing mother information
            Required fields:
                - name: str
                - age: int
                - phone: str
                - telegram_chat_id: str
            Optional fields:
                - assigned_asha_id: ObjectId
                - assigned_doctor_id: ObjectId
                - medical_history: dict
                - current_pregnancy: dict
                - address: dict
    
    Returns:
        ObjectId of the created mother
    """
    mothers = get_collection('mothers')
    
    # Set default values
    mother_data.setdefault('registered_at', datetime.utcnow())
    mother_data.setdefault('last_active', datetime.utcnow())
    mother_data.setdefault('active', True)
    
    result = mothers.insert_one(mother_data)
    return result.inserted_id


def get_by_id(mother_id):
    """
    Get a mother by ObjectId.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        Mother document or None if not found
    """
    mothers = get_collection('mothers')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    return mothers.find_one({'_id': mother_id})

# Alias for consistency
find_by_id = get_by_id

def get_by_telegram_chat_id(telegram_chat_id):
    """
    Get a mother by Telegram chat ID.
    
    Args:
        telegram_chat_id: Telegram chat ID (string or int)
    
    Returns:
        Mother document or None if not found
    """
    mothers = get_collection('mothers')
    return mothers.find_one({'telegram_chat_id': str(telegram_chat_id)})


def list_by_asha(asha_id):
    """
    List all mothers assigned to a specific ASHA worker.
    
    Args:
        asha_id: ObjectId or string representation
    
    Returns:
        List of mother documents
    """
    mothers = get_collection('mothers')
    
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    
    return list(mothers.find({'assigned_asha_id': asha_id, 'active': True}))


def list_by_doctor(doctor_id):
    """
    List all mothers assigned to a specific doctor.
    
    Args:
        doctor_id: ObjectId or string representation
    
    Returns:
        List of mother documents
    """
    mothers = get_collection('mothers')
    
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    
    return list(mothers.find({'assigned_doctor_id': doctor_id, 'active': True}))


def list_all_active():
    """
    List all active mothers.
    
    Returns:
        List of active mother documents
    """
    mothers = get_collection('mothers')
    return list(mothers.find({'active': True}))


def update(mother_id, update_data):
    """
    Update a mother's profile.
    
    Args:
        mother_id: ObjectId or string representation
        update_data: Dictionary of fields to update
    
    Returns:
        True if updated, False if not found
    """
    mothers = get_collection('mothers')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    # Update last_active timestamp
    update_data['last_active'] = datetime.utcnow()
    
    result = mothers.update_one(
        {'_id': mother_id},
        {'$set': update_data}
    )
    
    return result.modified_count > 0


def assign_asha(mother_id, asha_id):
    """
    Assign an ASHA worker to a mother.
    
    Args:
        mother_id: ObjectId or string representation
        asha_id: ObjectId or string representation
    
    Returns:
        True if updated, False if not found
    """
    if isinstance(asha_id, str):
        asha_id = ObjectId(asha_id)
    
    return update(mother_id, {'assigned_asha_id': asha_id})


def assign_doctor(mother_id, doctor_id):
    """
    Assign a doctor to a mother.
    
    Args:
        mother_id: ObjectId or string representation
        doctor_id: ObjectId or string representation
    
    Returns:
        True if updated, False if not found
    """
    if isinstance(doctor_id, str):
        doctor_id = ObjectId(doctor_id)
    
    return update(mother_id, {'assigned_doctor_id': doctor_id})


def deactivate(mother_id):
    """
    Deactivate a mother (e.g., after delivery or system exit).
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        True if deactivated, False if not found
    """
    return update(mother_id, {'active': False})
