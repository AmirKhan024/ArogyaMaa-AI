"""
Registration Repository

Data access layer for the 'registration_sessions' table (Postgres).
Manages in-progress AI registration sessions (state kept in a JSONB ``data`` column,
keyed by telegram_chat_id) and finalizes them into the 'mothers' table.
"""

from app.repositories import mothers_repo
from app.repositories._sql import exec_write, fetch_one, utcnow
from app.db import to_jsonb


def _age_from_dob(dob_text):
    """Compute age in years from a free-form date-of-birth string, or None."""
    try:
        import dateparser
        born = dateparser.parse(str(dob_text), settings={"DATE_ORDER": "DMY"})
        if not born:
            return None
        today = utcnow()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return age if 5 <= age <= 70 else None
    except Exception:
        return None


def get_session(telegram_chat_id):
    """Return the in-progress registration session data (dict) or None."""
    row = fetch_one(
        "select data from registration_sessions where telegram_chat_id = :cid",
        {"cid": str(telegram_chat_id)},
    )
    if not row:
        return None
    data = row.get("data") or {}
    data.setdefault("telegram_chat_id", str(telegram_chat_id))
    return data


def update_session_data(telegram_chat_id, new_data):
    """Create or merge a registration session (JSONB deep-merge on the data column)."""
    new_data = dict(new_data)
    new_data["telegram_chat_id"] = str(telegram_chat_id)
    exec_write(
        "insert into registration_sessions (telegram_chat_id, data, updated_at) "
        "values (:cid, cast(:data as jsonb), now()) "
        "on conflict (telegram_chat_id) do update set "
        "data = registration_sessions.data || cast(:data as jsonb), updated_at = now()",
        {"cid": str(telegram_chat_id), "data": to_jsonb(new_data)},
    )


def delete_session(telegram_chat_id):
    exec_write(
        "delete from registration_sessions where telegram_chat_id = :cid",
        {"cid": str(telegram_chat_id)},
    )


def finalize_registration(telegram_chat_id):
    """
    Move registration session data into the mothers table, then clear the session.
    Returns True if finalized.
    """
    session = get_session(telegram_chat_id)
    if not session:
        return False

    update_data = {
        "registration_complete": True,
        "registration_source": "ai_bot",
        "registration_completed_at": utcnow().isoformat(),
        "updated_at": utcnow().isoformat(),
    }

    # Direct field mappings
    if session.get("full_name"):
        update_data["name"] = session["full_name"]
    if session.get("age"):
        update_data["age"] = session["age"]
    elif session.get("dob"):
        # The LLM doesn't always derive age from dob — compute it deterministically
        # so downstream checks (e.g. appointment pre-fill) don't fail on age=None.
        derived_age = _age_from_dob(session["dob"])
        if derived_age is not None:
            update_data["age"] = derived_age
    if session.get("phone_number"):
        update_data["phone"] = session["phone_number"]
    if session.get("location"):
        update_data["location"] = session["location"]
    if session.get("dob"):
        update_data["dob"] = session["dob"]
    if session.get("emergency_contact"):
        update_data["emergency_contact"] = session["emergency_contact"]
    if session.get("preferred_language"):
        update_data["preferred_language"] = session["preferred_language"]

    # Pregnancy-related fields (nested under current_pregnancy)
    pregnancy_data = {}
    if session.get("gestational_week"):
        pregnancy_data["gestational_age_weeks"] = session["gestational_week"]
        update_data["gestational_age"] = session["gestational_week"]
    if session.get("lmp_date"):
        pregnancy_data["lmp_date"] = session["lmp_date"]
    if session.get("edd_date"):
        pregnancy_data["edd"] = session["edd_date"]
        update_data["edd"] = session["edd_date"]
    if session.get("first_pregnancy"):
        pregnancy_data["first_pregnancy"] = session["first_pregnancy"]
    if session.get("previous_pregnancies_count"):
        pregnancy_data["previous_pregnancies_count"] = session["previous_pregnancies_count"]
    if session.get("fetal_movement"):
        pregnancy_data["fetal_movement"] = session["fetal_movement"]
    if pregnancy_data:
        update_data["current_pregnancy"] = pregnancy_data

    # Medical history fields (nested under medical_history)
    medical_data = {}
    if session.get("blood_group"):
        medical_data["blood_group"] = session["blood_group"]
    if session.get("previous_complications"):
        medical_data["previous_complications"] = session["previous_complications"]
    if session.get("medical_conditions"):
        medical_data["conditions"] = session["medical_conditions"]
    if session.get("medications_supplements"):
        medical_data["medications_supplements"] = session["medications_supplements"]
    if session.get("allergies"):
        medical_data["allergies"] = session["allergies"]
    if session.get("major_surgeries"):
        medical_data["major_surgeries"] = session["major_surgeries"]
    if session.get("vaccines_received"):
        medical_data["vaccines_received"] = session["vaccines_received"]
    if session.get("scans_done"):
        medical_data["scans_done"] = session["scans_done"]
    if session.get("lab_tests_done"):
        medical_data["lab_tests_done"] = session["lab_tests_done"]
    if medical_data:
        update_data["medical_history"] = medical_data

    # Health status fields
    for key in ("current_symptoms", "danger_signs", "substance_usage", "doctor_consent"):
        if session.get(key):
            update_data[key] = session[key]

    existing = mothers_repo.get_by_telegram_chat_id(telegram_chat_id)
    if existing:
        mothers_repo.update(existing["_id"], update_data)
    else:
        update_data["telegram_chat_id"] = str(telegram_chat_id)
        mothers_repo.create(update_data)

    delete_session(telegram_chat_id)
    return True
