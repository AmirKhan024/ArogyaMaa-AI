"""
Shared logic for ArogyaMaa Dashboards
Common data preparation for views used by both Doctors and ASHA workers.
"""

import traceback
from bson import ObjectId
from datetime import datetime
from app.repositories import mothers_repo, assessments_repo


def _safe_str(val, default='N/A'):
    """Convert any value to a non-empty string, or return default."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def get_clinical_portfolio_context(mother_id):
    """
    Prepare data for the 'Clinical Portfolio' (Patient Profile) view.
    Used by both ASHA and Doctor blueprints.
    Bulletproof: returns None only if mother does not exist in DB.
    Schema-aware: reads fields from the actual Telegram-registered document layout.
    """
    # --- Step 1: Fetch Mother ---
    try:
        mother = mothers_repo.get_by_id(mother_id)
    except Exception as e:
        print(f"[PORTFOLIO] CRITICAL: mothers_repo.get_by_id({mother_id}) raised: {e}")
        print(traceback.format_exc())
        return None

    if not mother:
        print(f"[PORTFOLIO] Mother {mother_id} not found in 'mothers' collection")
        return None

    # --- Step 2: Fetch Assessments (non-fatal) ---
    latest_assessment = None
    history = []
    try:
        latest_assessment = assessments_repo.get_latest_for_mother(mother_id)
    except Exception as e:
        print(f"[PORTFOLIO] WARNING: get_latest_for_mother failed: {e}")

    try:
        history = list(assessments_repo.list_by_mother(mother_id, limit=20))
        history.reverse()
    except Exception as e:
        print(f"[PORTFOLIO] WARNING: list_by_mother failed: {e}")
        history = []

    # --- Step 3: Extract Risk Data ---
    risk_score = 0
    risk_status = 'LOW'
    ai_summary = {
        'reasoning': 'No assessments performed yet.',
        'recommendations': []
    }

    try:
        if latest_assessment:
            ai_eval = latest_assessment.get('ai_evaluation') or {}
            risk_score = int(ai_eval.get('risk_score') or 0)
            risk_status = str(ai_eval.get('risk_category') or 'LOW')
            reasoning = ai_eval.get('reasoning') or 'No reasoning provided.'
            recommendations = ai_eval.get('recommended_actions') or []
            ai_summary = {
                'reasoning': reasoning,
                'recommendations': recommendations if isinstance(recommendations, list) else []
            }
    except Exception as e:
        print(f"[PORTFOLIO] WARNING: risk extraction failed: {e}")

    # --- Step 4: Clinical Factors ---
    # Supports two schema shapes:
    #  A) Telegram schema: medical_history = { blood_group, previous_complications,
    #                       conditions, medications_supplements, allergies, ... }
    #  B) Legacy schema:   medical_history = { blood_group, previous_pregnancies,
    #                       past_complications, height, weight, ... }
    med_hist = {}
    try:
        med_hist = mother.get('medical_history') or {}
    except Exception:
        pass

    pregnancy_info = {}
    try:
        pregnancy_info = mother.get('current_pregnancy') or {}
    except Exception:
        pass

    # Previous pregnancies — check multiple locations across schema variants
    prev_preg = (
        med_hist.get('previous_pregnancies')
        or med_hist.get('previous_pregnancies_count')
        or pregnancy_info.get('previous_pregnancies_count')
        or pregnancy_info.get('previous_pregnancies')
        or '0'
    )

    # Past complications — check both naming conventions
    past_comp = (
        med_hist.get('past_complications')
        or med_hist.get('previous_complications')
        or 'None reported'
    )

    clinical_factors = {
        "Previous Pregnancies": _safe_str(prev_preg, '0'),
        "Past Complications": _safe_str(past_comp, 'None reported'),
        "Height (cm)": _safe_str(med_hist.get('height'), 'N/A'),
        "Weight (kg)": _safe_str(med_hist.get('weight'), 'N/A')
    }

    # Conditions — check both naming conventions
    conditions = (
        med_hist.get('chronic_conditions')
        or med_hist.get('conditions')
        or 'None reported'
    )
    # Medications — check both naming conventions
    medications = (
        med_hist.get('current_medications')
        or med_hist.get('medications_supplements')
        or 'None reported'
    )

    background_factors = {
        "Chronic Conditions": _safe_str(conditions, 'None reported'),
        "Allergies": _safe_str(med_hist.get('allergies'), 'None reported'),
        "Current Medications": _safe_str(medications, 'None reported'),
        "Family History": _safe_str(med_hist.get('family_medical_history'), 'None reported')
    }

    screening_raw = med_hist.get('screening_status')
    if isinstance(screening_raw, dict):
        screening_status = screening_raw
    else:
        screening_status = {"Anemia": "No", "Diabetes": "No", "Hypertension": "No", "HIV/Syphilis": "No"}

    # --- Step 5: Chart Data ---
    graph_weeks = []
    graph_scores = []
    try:
        for entry in history:
            try:
                ts = entry.get('timestamp')
                if ts and hasattr(ts, 'strftime'):
                    date_str = ts.strftime('%d %b')
                elif ts:
                    date_str = str(ts)[:10]
                else:
                    date_str = '?'
                graph_weeks.append(date_str)
                ae = entry.get('ai_evaluation') or {}
                graph_scores.append(int(ae.get('risk_score') or 0))
            except Exception:
                graph_weeks.append('?')
                graph_scores.append(0)
    except Exception as e:
        print(f"[PORTFOLIO] WARNING: chart data build failed: {e}")

    # --- Step 6: Current State ---
    # Prefer values from latest assessment, fall back to root-level fields (Telegram schema)
    current_symptoms = 'None reported'
    danger_signs = 'No'
    try:
        if latest_assessment:
            symptoms = latest_assessment.get('symptoms') or []
            if isinstance(symptoms, list) and symptoms:
                current_symptoms = ", ".join(str(s) for s in symptoms)
            danger_signs = str(latest_assessment.get('danger_signs_present') or 'No')
        else:
            # Root-level fields set during Telegram registration
            cs = mother.get('current_symptoms')
            if cs and str(cs).strip().lower() not in ('', 'nothing', 'none'):
                current_symptoms = str(cs)
            ds = mother.get('danger_signs')
            if ds:
                danger_signs = str(ds)
    except Exception as e:
        print(f"[PORTFOLIO] WARNING: current state extraction failed: {e}")

    # --- Step 7: Assemble Patient Info ---
    try:
        # Location: try nested address dict first, then root 'location' string
        address_info = mother.get('address') or {}
        location = (
            address_info.get('village')
            or address_info.get('city')
            or mother.get('location')
            or 'Unknown'
        )

        # EDD: try current_pregnancy first, then root-level 'edd'
        edd_date = (
            pregnancy_info.get('edd')
            or mother.get('edd')
            or 'Calculating...'
        )

        # Gestational week: try assessment first, then current_pregnancy, then root
        gestational_week = '0'
        try:
            if latest_assessment and latest_assessment.get('gestational_age_at_assessment'):
                gestational_week = str(latest_assessment['gestational_age_at_assessment'])
            elif pregnancy_info.get('gestational_age_weeks'):
                gestational_week = str(pregnancy_info['gestational_age_weeks'])
            elif mother.get('gestational_age'):
                gestational_week = str(mother['gestational_age'])
        except Exception:
            pass

        # Blood group
        blood_group = _safe_str(med_hist.get('blood_group'), 'Unknown')

        # First pregnancy — check multiple sources
        first_preg_flag = (
            pregnancy_info.get('first_pregnancy')
            or med_hist.get('first_pregnancy')
        )
        prev_count = (
            pregnancy_info.get('previous_pregnancies_count')
            or med_hist.get('previous_pregnancies')
            or prev_preg
        )
        if first_preg_flag and str(first_preg_flag).strip().lower() == 'yes':
            first_pregnancy_label = "Yes"
        elif prev_count is not None and str(prev_count).strip() in ('0', '0.0'):
            first_pregnancy_label = "Yes"
        else:
            first_pregnancy_label = "No"

        # Emergency contact: root-level string (Telegram schema) OR nested dict (legacy schema)
        raw_ec = mother.get('emergency_contact')
        if isinstance(raw_ec, dict):
            emergency_contact = raw_ec.get('phone') or raw_ec.get('number') or 'Not Provided'
        elif raw_ec:
            emergency_contact = str(raw_ec)
        else:
            emergency_contact = 'Not Provided'

        patient_info = {
            "id": str(mother.get('_id', '')),
            "full_name": _safe_str(mother.get('name'), 'Unknown'),
            "phone_number": _safe_str(mother.get('phone'), 'No Phone'),
            "location": _safe_str(location, 'Unknown'),
            "age": _safe_str(mother.get('age'), 'N/A'),
            "gestational_week": gestational_week,
            "edd_date": _safe_str(edd_date, 'Calculating...'),
            "blood_group": blood_group,
            "first_pregnancy": first_pregnancy_label,
            "current_symptoms": current_symptoms,
            "danger_signs": danger_signs,
            "emergency_contact": emergency_contact,
            "telegram_id": mother.get('telegram_chat_id')
        }

    except Exception as e:
        print(f"[PORTFOLIO] CRITICAL: patient_info assembly failed: {e}")
        print(traceback.format_exc())
        # Absolute fallback — always show something real from the DB record
        patient_info = {
            "id": str(mother.get('_id', '')),
            "full_name": _safe_str(mother.get('name'), 'Unknown Patient'),
            "phone_number": _safe_str(mother.get('phone'), 'N/A'),
            "location": _safe_str(mother.get('location'), 'N/A'),
            "age": _safe_str(mother.get('age'), 'N/A'),
            "gestational_week": _safe_str(mother.get('gestational_age'), '0'),
            "edd_date": _safe_str(mother.get('edd'), 'N/A'),
            "blood_group": "N/A",
            "first_pregnancy": "No",
            "current_symptoms": _safe_str(mother.get('current_symptoms'), 'N/A'),
            "danger_signs": _safe_str(mother.get('danger_signs'), 'No'),
            "emergency_contact": _safe_str(mother.get('emergency_contact'), 'N/A'),
            "telegram_id": mother.get('telegram_chat_id')
        }

    context = {
        "patient": patient_info,
        "risk_status": risk_status,
        "risk_score": risk_score,
        "ai_summary": ai_summary,
        "factors": {
            "clinical": clinical_factors,
            "background": background_factors,
            "screening": screening_status
        },
        "graph_weeks": graph_weeks,
        "graph_scores": graph_scores
    }

    return context
