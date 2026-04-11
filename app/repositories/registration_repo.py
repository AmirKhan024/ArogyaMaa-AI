"""
Registration Repository

Data access layer for the 'registration_sessions' collection.
Manages in-progress AI registration sessions and finalizes them
into the 'mothers' collection.
"""

from datetime import datetime
from app.db import get_collection


def get_session(telegram_chat_id):
    """
    Get an in-progress registration session.

    Args:
        telegram_chat_id: Telegram chat ID (string)

    Returns:
        dict or None: Session data
    """
    sessions = get_collection('registration_sessions')
    return sessions.find_one({"telegram_chat_id": str(telegram_chat_id)})


def update_session_data(telegram_chat_id, new_data):
    """
    Update or create a registration session with new data.

    Args:
        telegram_chat_id: Telegram chat ID (string)
        new_data: Dictionary of fields to set/update
    """
    sessions = get_collection('registration_sessions')
    # Ensure telegram_chat_id is always stored as string
    new_data['telegram_chat_id'] = str(telegram_chat_id)
    sessions.update_one(
        {"telegram_chat_id": str(telegram_chat_id)},
        {"$set": new_data},
        upsert=True
    )


def delete_session(telegram_chat_id):
    """
    Delete a registration session after finalization.

    Args:
        telegram_chat_id: Telegram chat ID (string)
    """
    sessions = get_collection('registration_sessions')
    sessions.delete_one({"telegram_chat_id": str(telegram_chat_id)})


def finalize_registration(telegram_chat_id):
    """
    Move registration session data into the mothers collection.

    Merges the detailed registration data into the existing mother
    profile (created on /start). Uses update_one with upsert to
    avoid duplicates.

    Args:
        telegram_chat_id: Telegram chat ID (string)

    Returns:
        bool: True if finalized successfully
    """
    session = get_session(telegram_chat_id)
    if not session:
        return False

    mothers = get_collection('mothers')

    # Build the update data, mapping session fields to mother schema
    update_data = {
        'registration_complete': True,
        'registration_source': 'ai_bot',
        'registration_completed_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }

    # Direct field mappings
    if session.get('full_name'):
        update_data['name'] = session['full_name']
    if session.get('age'):
        update_data['age'] = session['age']
    if session.get('phone_number'):
        update_data['phone'] = session['phone_number']
    if session.get('location'):
        update_data['location'] = session['location']
    if session.get('dob'):
        update_data['dob'] = session['dob']
    if session.get('emergency_contact'):
        update_data['emergency_contact'] = session['emergency_contact']
    if session.get('preferred_language'):
        update_data['preferred_language'] = session['preferred_language']

    # Pregnancy-related fields
    pregnancy_data = {}
    if session.get('gestational_week'):
        pregnancy_data['gestational_age_weeks'] = session['gestational_week']
        update_data['gestational_age'] = session['gestational_week']
    if session.get('lmp_date'):
        pregnancy_data['lmp_date'] = session['lmp_date']
    if session.get('edd_date'):
        pregnancy_data['edd'] = session['edd_date']
        update_data['edd'] = session['edd_date']
    if session.get('first_pregnancy'):
        pregnancy_data['first_pregnancy'] = session['first_pregnancy']
    if session.get('previous_pregnancies_count'):
        pregnancy_data['previous_pregnancies_count'] = session['previous_pregnancies_count']
    if session.get('fetal_movement'):
        pregnancy_data['fetal_movement'] = session['fetal_movement']
    if pregnancy_data:
        update_data['current_pregnancy'] = pregnancy_data

    # Medical history fields
    medical_data = {}
    if session.get('blood_group'):
        medical_data['blood_group'] = session['blood_group']
    if session.get('previous_complications'):
        medical_data['previous_complications'] = session['previous_complications']
    if session.get('medical_conditions'):
        medical_data['conditions'] = session['medical_conditions']
    if session.get('medications_supplements'):
        medical_data['medications_supplements'] = session['medications_supplements']
    if session.get('allergies'):
        medical_data['allergies'] = session['allergies']
    if session.get('major_surgeries'):
        medical_data['major_surgeries'] = session['major_surgeries']
    if session.get('vaccines_received'):
        medical_data['vaccines_received'] = session['vaccines_received']
    if session.get('scans_done'):
        medical_data['scans_done'] = session['scans_done']
    if session.get('lab_tests_done'):
        medical_data['lab_tests_done'] = session['lab_tests_done']
    if medical_data:
        update_data['medical_history'] = medical_data

    # Health status fields
    if session.get('current_symptoms'):
        update_data['current_symptoms'] = session['current_symptoms']
    if session.get('danger_signs'):
        update_data['danger_signs'] = session['danger_signs']
    if session.get('substance_usage'):
        update_data['substance_usage'] = session['substance_usage']
    if session.get('doctor_consent'):
        update_data['doctor_consent'] = session['doctor_consent']

    # Update the existing mother record (or create if somehow missing)
    mothers.update_one(
        {"telegram_chat_id": str(telegram_chat_id)},
        {"$set": update_data},
        upsert=True
    )

    # Clean up the session
    delete_session(telegram_chat_id)

    return True
