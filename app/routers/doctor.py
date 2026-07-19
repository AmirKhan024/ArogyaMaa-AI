"""
Doctor Router — FastAPI port of app/blueprints/doctor/routes.py.

Doctors review assessments and enter consultation details.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body

from app.repositories import (
    mothers_repo,
    doctors_repo,
    assessments_repo,
    consultations_repo,
    messages_repo,
    documents_repo
)
from app.services import telegram_service
from app.routers._utils import json_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/doctor")


def _safe_iso(value):
    """Return ISO-format string for datetime or plain string dates; None if absent."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


@router.get("/health", name="doctor.health")
def health():
    """Health check endpoint for Doctor service"""
    return json_response({
        "service": "doctor",
        "status": "active"
    }, 200)


@router.get("/mothers", name="doctor.get_mothers")
def get_mothers(doctor_id: str = None):
    """Get list of mothers assigned to a doctor."""
    try:
        if not doctor_id:
            return json_response({
                "error": "doctor_id parameter is required"
            }, 400)

        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return json_response({
                "error": "Doctor not found"
            }, 404)

        mothers = mothers_repo.list_by_doctor(doctor_id)

        mothers_list = []
        for mother in mothers:
            latest_assessment = assessments_repo.get_latest_for_mother(mother['_id'])

            pregnancy = mother.get('current_pregnancy') or {}

            asha_name = 'Not Assigned'
            asha_id_raw = mother.get('assigned_asha_id')
            if asha_id_raw:
                try:
                    from app.repositories import asha_repo
                    asha_worker = asha_repo.get_by_id(str(asha_id_raw))
                    if asha_worker:
                        asha_name = asha_worker.get('name', 'Unknown ASHA')
                except Exception:
                    pass

            # EDD — safely handle str or datetime
            edd_val = pregnancy.get('edd') or pregnancy.get('edd_date')

            mother_data = {
                "mother_id": str(mother['_id']),
                "name": mother.get('name', 'Unknown'),
                "age": mother.get('age'),
                "phone": mother.get('phone'),
                "gestational_age_weeks": pregnancy.get('gestational_age_weeks') or mother.get('gestational_age'),
                "edd": _safe_iso(edd_val),
                "address": mother.get('address', {}),
                "asha_name": asha_name,
                "current_risk_level": 'N/A',
                "last_assessment_date": None,
                "pending_review_count": 0,
                "latest_assessment": None
            }

            if latest_assessment:
                ai_eval = latest_assessment.get('ai_evaluation') or {}

                # Use doctor's risk if reviewed, otherwise AI risk
                current_risk = ai_eval.get('risk_category', 'NOT_EVALUATED')
                if latest_assessment.get('reviewed_by_doctor'):
                    consultation_id = latest_assessment.get('consultation_id')
                    if consultation_id:
                        consultation = consultations_repo.get_by_id(consultation_id)
                        if consultation and consultation.get('doctor_risk_assessment'):
                            current_risk = consultation.get('doctor_risk_assessment')

                all_assessments = assessments_repo.list_by_mother(mother['_id'])
                pending_reviews = sum(1 for a in all_assessments if not a.get('reviewed_by_doctor'))

                mother_data['current_risk_level'] = current_risk
                mother_data['last_assessment_date'] = _safe_iso(latest_assessment.get('timestamp'))
                mother_data['pending_review_count'] = pending_reviews
                mother_data['latest_assessment'] = {
                    "assessment_id": str(latest_assessment['_id']),
                    "date": _safe_iso(latest_assessment.get('timestamp')),
                    "risk_category": current_risk,
                    "risk_score": ai_eval.get('risk_score'),
                    "reviewed": latest_assessment.get('reviewed_by_doctor', False),
                    "symptoms_count": len(latest_assessment.get('symptoms', [])),
                    "pending_reviews": pending_reviews
                }

            mothers_list.append(mother_data)

        return json_response({
            "doctor_id": doctor_id,
            "doctor_name": doctor.get('name'),
            "total_mothers": len(mothers_list),
            "mothers": mothers_list
        }, 200)

    except Exception as e:
        logger.error(f"Error fetching mothers for doctor: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch mothers",
            "details": str(e)
        }, 500)


@router.get("/assessments", name="doctor.get_assessments")
def get_assessments(mother_id: str = None, doctor_id: str = None, limit: int = 50):
    """Get assessment history for a specific mother OR pending assessments for a doctor."""
    try:
        assessments_list = []

        if mother_id:
            # Case 1: Get history for a specific mother
            mother = mothers_repo.get_by_id(mother_id)
            if not mother:
                return json_response({"error": "Mother not found"}, 404)

            common_mother_name = mother.get('name', 'Unknown')
            assessments = assessments_repo.list_by_mother(mother_id, limit=limit)

            # Context for ASHA name resolution (memoized — each DB round-trip to the
            # Supabase pooler costs ~0.5s, so N+1 lookups make the page crawl)
            from app.repositories import asha_repo
            asha_names = {}

            for assessment in assessments:
                inner_asha_id = str(assessment.get('asha_id') or '')
                if inner_asha_id and inner_asha_id not in asha_names:
                    asha_worker = asha_repo.get_by_id(inner_asha_id)
                    asha_names[inner_asha_id] = (asha_worker or {}).get('name', 'ASHA Worker')
                inner_asha_name = asha_names.get(inner_asha_id, 'ASHA Worker')

                assessments_list.append(_format_as_s_res(assessment, common_mother_name, inner_asha_name))

            return json_response({
                "mother_id": mother_id,
                "mother_name": common_mother_name,
                "mother_info": {
                    "name": common_mother_name,
                    "age": mother.get('age'),
                    "phone": mother.get('phone'),
                    "location": mother.get('location'),
                    "gestational_age_weeks": (
                        (mother.get('current_pregnancy') or {}).get('gestational_age_weeks')
                        or mother.get('gestational_age')
                    ),
                    "blood_group": (mother.get('medical_history') or {}).get('blood_group'),
                },
                "total_assessments": len(assessments_list),
                "assessments": assessments_list
            }, 200)

        elif doctor_id:
            # Case 2: Get all pending assessments for a doctor (Dashboard view)
            assessments = assessments_repo.list_pending_doctor_review(doctor_id, limit=limit)

            from app.repositories import asha_repo
            # Memoize name lookups — without this the page does 2 pooler round-trips
            # PER assessment (~20s for 18 rows).
            mother_names, asha_names = {}, {}

            for assessment in assessments:
                m_id = str(assessment.get('mother_id') or '')
                if m_id and m_id not in mother_names:
                    m_obj = mothers_repo.get_by_id(m_id)
                    mother_names[m_id] = (m_obj or {}).get('name', 'Unknown')
                m_name = mother_names.get(m_id, 'Unknown')

                a_id = str(assessment.get('asha_id') or '')
                if a_id and a_id not in asha_names:
                    a_obj = asha_repo.get_by_id(a_id)
                    asha_names[a_id] = (a_obj or {}).get('name', 'ASHA Worker')
                a_name = asha_names.get(a_id, 'ASHA Worker')

                assessments_list.append(_format_as_s_res(assessment, m_name, a_name))

            return json_response({
                "doctor_id": doctor_id,
                "total_assessments": len(assessments_list),
                "assessments": assessments_list
            }, 200)

        else:
            return json_response({
                "error": "Either mother_id or doctor_id parameter is required"
            }, 400)

    except Exception as e:
        logger.error(f"Error fetching assessments: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch assessments",
            "details": str(e)
        }, 500)


def _format_as_s_res(assessment, mother_name, asha_name):
    """Internal helper to format assessment data for list views"""
    ai_eval = assessment.get('ai_evaluation', {})

    doctor_consultation = None
    if assessment.get('reviewed_by_doctor') and assessment.get('consultation_id'):
        from app.repositories import consultations_repo
        consultation = consultations_repo.get_by_id(assessment.get('consultation_id'))
        if consultation:
            doctor_consultation = {
                "diagnosis": consultation.get('diagnosis'),
                "doctor_risk_assessment": consultation.get('doctor_risk_assessment'),
                "timestamp": _safe_iso(consultation.get('created_at'))
            }

    return {
        "assessment_id": str(assessment['_id']),
        "assessment_number": assessment.get('assessment_number'),
        "timestamp": _safe_iso(assessment.get('timestamp')),
        "mother_id": str(assessment.get('mother_id')),
        "mother_name": mother_name,
        "asha_id": str(assessment.get('asha_id')),
        "asha_name": asha_name,
        "gestational_age_weeks": assessment.get('gestational_age_at_assessment'),
        "vitals": assessment.get('vitals', {}),
        "symptoms": assessment.get('symptoms', []),
        "ai_evaluation": {
            "risk_score": ai_eval.get('risk_score'),
            "risk_category": ai_eval.get('risk_category', 'NOT_EVALUATED'),
            "confidence": ai_eval.get('confidence'),
            "evaluation_method": ai_eval.get('evaluation_method'),
            "agent_outputs": ai_eval.get('agent_outputs', {}),
            "recommended_actions": ai_eval.get('recommended_actions', [])
        } if ai_eval else None,
        "doctor_reviewed": assessment.get('reviewed_by_doctor', False),
        "doctor_consultation": doctor_consultation
    }


@router.get("/assessment/{assessment_id}", name="doctor.get_assessment_by_id")
def get_assessment_by_id(assessment_id: str, doctor_id: str = None):
    """Get a single assessment by ID with full details including consultation."""
    try:
        assessment = assessments_repo.get_by_id(assessment_id)
        if not assessment:
            return json_response({
                "error": "Assessment not found"
            }, 404)

        mother = mothers_repo.get_by_id(assessment['mother_id'])

        asha_name = 'ASHA Worker'
        asha_id = assessment.get('asha_id')
        if asha_id:
            from app.repositories import asha_repo
            asha_worker = asha_repo.get_by_id(asha_id)
            if asha_worker:
                asha_name = asha_worker.get('name', 'ASHA Worker')

        ai_eval = assessment.get('ai_evaluation', {})

        doctor_consultation = None
        if assessment.get('reviewed_by_doctor') and assessment.get('consultation_id'):
            consultation = consultations_repo.get_by_id(assessment.get('consultation_id'))
            if consultation:
                doctor = doctors_repo.get_by_id(consultation.get('doctor_id'))

                # Handle treatment_plan - can be string or dict
                treatment_plan_data = consultation.get('treatment_plan', {})
                if isinstance(treatment_plan_data, dict):
                    treatment_plan_text = treatment_plan_data.get('follow_up_instructions') or str(treatment_plan_data)
                    prescriptions = treatment_plan_data.get('medications')
                else:
                    treatment_plan_text = str(treatment_plan_data)
                    prescriptions = None

                doctor_consultation = {
                    "diagnosis": consultation.get('diagnosis'),
                    "observations": consultation.get('clinical_observations'),
                    "treatment_plan": treatment_plan_text,
                    "doctor_risk_assessment": consultation.get('doctor_risk_assessment'),
                    "doctor_name": doctor.get('name') if doctor else 'Unknown',
                    "timestamp": consultation.get('created_at').isoformat() if consultation.get('created_at') else None,
                    "ai_overridden": consultation.get('overrides_ai_assessment', False),
                    "override_reason": consultation.get('override_reason'),
                    "prescriptions": prescriptions,
                    "follow_up_date": consultation.get('next_visit_date').isoformat() if consultation.get('next_visit_date') else None,
                    "updated_vitals": consultation.get('updated_vitals')
                }

        assessment_data = {
            "assessment_id": str(assessment['_id']),
            "assessment_number": assessment.get('assessment_number'),
            "timestamp": assessment.get('timestamp').isoformat() if assessment.get('timestamp') else None,
            "asha_id": str(assessment.get('asha_id')) if assessment.get('asha_id') else None,
            "asha_name": asha_name,
            "gestational_age_weeks": assessment.get('gestational_age_at_assessment'),
            "vitals": assessment.get('vitals', {}),
            "symptoms": assessment.get('symptoms', []),
            "asha_notes": assessment.get('asha_notes', ''),
            "ai_evaluation": {
                "risk_score": ai_eval.get('risk_score'),
                "risk_category": ai_eval.get('risk_category', 'NOT_EVALUATED'),
                "confidence": ai_eval.get('confidence'),
                "recommended_actions": ai_eval.get('recommended_actions', []),
                "agent_outputs": ai_eval.get('agent_outputs'),
                "reasoning": ai_eval.get('reasoning')
            } if ai_eval else None,
            "doctor_reviewed": assessment.get('reviewed_by_doctor', False),
            "doctor_reviewed_at": assessment.get('doctor_reviewed_at').isoformat() if assessment.get('doctor_reviewed_at') else None,
            "doctor_consultation": doctor_consultation,
            "mother_info": {
                "mother_id": str(mother['_id']) if mother else None,
                "name": mother.get('name') if mother else 'Unknown',
                "age": mother.get('age') if mother else None,
                "phone": mother.get('phone') if mother else None
            }
        }

        return json_response(assessment_data, 200)

    except Exception as e:
        logger.error(f"Error fetching assessment: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch assessment",
            "details": str(e)
        }, 500)


@router.post("/consultation", name="doctor.submit_consultation")
def submit_consultation(data: dict = Body(None)):
    """Submit consultation details for an assessment."""
    try:
        data = data or {}

        required_fields = ['assessment_id', 'doctor_id', 'diagnosis']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return json_response({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }, 400)

        assessment_id = data['assessment_id']
        doctor_id = data['doctor_id']

        assessment = assessments_repo.get_by_id(assessment_id)
        if not assessment:
            return json_response({
                "error": "Assessment not found"
            }, 404)

        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return json_response({
                "error": "Doctor not found"
            }, 404)

        mother_id = assessment['mother_id']
        mother = mothers_repo.get_by_id(mother_id)

        next_visit_date = None
        if data.get('next_visit_date'):
            try:
                next_visit_date = datetime.fromisoformat(data['next_visit_date'].replace('Z', '+00:00'))
            except Exception:
                next_visit_date = None

        consultation_data = {
            'assessment_id': str(assessment_id),
            'mother_id': str(mother_id),
            'doctor_id': str(doctor_id),
            'diagnosis': data['diagnosis'],
            'clinical_observations': data.get('clinical_observations', ''),
            'updated_vitals': data.get('updated_vitals', {}),
            'treatment_plan': data.get('treatment_plan', {}),
            'next_visit_date': next_visit_date,
            'overrides_ai_assessment': data.get('overrides_ai_assessment', False),
            'doctor_risk_assessment': data.get('doctor_risk_assessment'),
            'override_reason': data.get('override_reason', ''),
            'consultation_notes': data.get('consultation_notes', '')
        }

        consultation_id = consultations_repo.create(consultation_data)

        assessments_repo.mark_as_reviewed(assessment_id, consultation_id, doctor_id)

        is_high_risk = assessment.get('ai_evaluation', {}).get('risk_category') == 'HIGH'
        doctors_repo.increment_consultation_count(doctor_id, is_high_risk=is_high_risk)

        # Prepare detailed message for mother (includes diagnosis, treatment, next visit)
        treatment_plan_text = data.get('treatment_plan', '')
        if isinstance(treatment_plan_text, dict):
            treatment_plan_text = treatment_plan_text.get('plan', '') or treatment_plan_text.get('medications', '') or str(treatment_plan_text)

        mother_message = f"""
🩺 <b>Health Update from Your Doctor</b>

Hello {mother.get('name', 'Mother')},

Your doctor has reviewed your recent checkup.

<b>Diagnosis:</b>
{data.get('diagnosis', 'Under review')}

<b>Treatment Plan:</b>
{treatment_plan_text or 'Your ASHA worker will share details'}

<b>Next Visit:</b> {next_visit_date.strftime('%d %B %Y') if next_visit_date else 'Will be scheduled soon'}

Your ASHA worker will contact you with any additional details. If you have concerns, please reach out.

Take care! 💚
"""

        telegram_sent = False
        telegram_error = None
        if mother.get('telegram_chat_id'):
            try:
                telegram_service.send_message(mother['telegram_chat_id'], mother_message)
                telegram_sent = True
            except Exception as telegram_err:
                logger.error(f"Telegram send failed: {telegram_err}")
                telegram_error = str(telegram_err)
                # Don't block workflow if Telegram fails

            try:
                messages_repo.create({
                    'mother_id': str(mother_id),
                    'mother_name': mother.get('name'),
                    'from_doctor': True,
                    'doctor_name': doctor.get('name'),
                    'message_type': 'doctor_consultation',
                    'content': mother_message,
                    'message': mother_message,
                    'read': False,
                })
            except Exception as log_err:
                logger.error(f"Failed to log message: {log_err}")

        return json_response({
            "status": "success",
            "message": "Consultation submitted successfully",
            "consultation_id": str(consultation_id),
            "assessment_marked_reviewed": True,
            "mother_notified": telegram_sent,
            "notification_error": telegram_error
        }, 201)

    except Exception as e:
        logger.error(f"Error submitting consultation: {e}", exc_info=True)
        return json_response({
            "error": "Failed to submit consultation",
            "details": str(e)
        }, 500)


@router.get("/appointments", name="doctor.list_appointments")
def list_appointments(doctor_id: str = None, status: str = None):
    """All appointment requests (Telegram bookings), newest first."""
    try:
        if not doctor_id:
            return json_response({"error": "doctor_id is required"}, 400)
        if not doctors_repo.get_by_id(doctor_id):
            return json_response({"error": "Doctor not found"}, 404)

        from app.repositories import appointments_repo
        rows = appointments_repo.list_all(status=status)

        items = []
        for a in rows:
            items.append({
                "appointment_id": a.get('appointment_id'),
                "patient_name": a.get('patient_name'),
                "patient_age": a.get('patient_age'),
                "patient_phone": a.get('patient_phone'),
                "mother_id": str(a.get('mother_id')) if a.get('mother_id') else None,
                "preferred_date": a.get('preferred_date'),
                "preferred_time": a.get('preferred_time'),
                "symptoms": a.get('symptoms'),
                "status": a.get('status'),
                "confirmed_date": a.get('confirmed_date'),
                "confirmed_time": a.get('confirmed_time'),
                "doctor_notes": a.get('doctor_notes'),
                "created_at": a.get('created_at'),
            })
        return json_response({"appointments": items, "total": len(items)}, 200)

    except Exception as e:
        logger.error(f"Error listing appointments: {e}", exc_info=True)
        return json_response({"error": str(e)}, 500)


@router.post("/appointments/{appointment_id}/action", name="doctor.appointment_action")
def appointment_action(appointment_id: str, data: dict = Body(None)):
    """Confirm / reschedule / cancel an appointment from the dashboard and notify
    the mother on Telegram in her language."""
    try:
        data = data or {}
        doctor_id = data.get('doctor_id')
        action = (data.get('action') or '').lower()

        if not doctor_id or not doctors_repo.get_by_id(doctor_id):
            return json_response({"error": "Valid doctor_id is required"}, 400)
        if action not in ('confirm', 'reschedule', 'cancel'):
            return json_response({"error": "action must be confirm, reschedule or cancel"}, 400)

        from app.repositories import appointments_repo
        from appointment.webhook_server import (
            build_confirmed_message, build_rescheduled_message, build_cancelled_message,
        )

        existing = appointments_repo.get_by_appointment_id(appointment_id)
        if not existing:
            return json_response({"error": "Appointment not found"}, 404)

        if action == 'confirm':
            updated = appointments_repo.update_status(
                appointment_id, "Confirmed",
                confirmed_date=data.get('date') or existing.get('preferred_date'),
                confirmed_time=data.get('time') or existing.get('preferred_time'),
                doctor_notes=data.get('notes', ''),
            )
            patient_msg = build_confirmed_message(updated)
        elif action == 'reschedule':
            if not data.get('date') or not data.get('time'):
                return json_response({"error": "date and time are required for reschedule"}, 400)
            updated = appointments_repo.update_status(
                appointment_id, "Rescheduled",
                confirmed_date=data['date'], confirmed_time=data['time'],
                doctor_notes=data.get('notes', ''),
            )
            patient_msg = build_rescheduled_message(updated)
        else:  # cancel
            updated = appointments_repo.update_status(
                appointment_id, "Cancelled", doctor_notes=data.get('notes', ''),
            )
            patient_msg = build_cancelled_message(updated)

        # Notify the mother on Telegram (non-fatal; works from the web process).
        notified = False
        chat_id = updated.get('telegram_chat_id')
        if chat_id:
            try:
                resp = telegram_service.send_message(chat_id, patient_msg)
                notified = bool(resp and resp.get('ok'))
            except Exception as e:
                logger.error(f"[Appointments] Patient notify failed: {e}")

        return json_response({
            "status": "success",
            "appointment": {
                "appointment_id": updated.get('appointment_id'),
                "status": updated.get('status'),
                "confirmed_date": updated.get('confirmed_date'),
                "confirmed_time": updated.get('confirmed_time'),
            },
            "patient_notified": notified,
        }, 200)

    except Exception as e:
        logger.error(f"Error acting on appointment: {e}", exc_info=True)
        return json_response({"error": str(e)}, 500)


@router.get("/messages", name="doctor.list_messages")
def list_messages(doctor_id: str = None, limit: int = 50):
    """Inbox for the doctor: notifications addressed to them, newest first."""
    try:
        if not doctor_id:
            return json_response({"error": "doctor_id is required"}, 400)
        if not doctors_repo.get_by_id(doctor_id):
            return json_response({"error": "Doctor not found"}, 404)

        notifications = messages_repo.list_by_recipient(doctor_id, 'doctor', limit=limit)

        items = []
        for n in notifications:
            items.append({
                "id": str(n.get('_id')),
                "mother_id": str(n.get('mother_id')) if n.get('mother_id') else None,
                "mother_name": n.get('mother_name') or 'Unknown',
                "message_type": n.get('message_type') or 'note',
                "content": n.get('content') or n.get('message') or '',
                "subject": n.get('subject'),
                "is_alert": bool(n.get('is_alert')),
                "alert_type": n.get('alert_type'),
                "related_assessment_id": (
                    str(n.get('related_assessment_id'))
                    if n.get('related_assessment_id') else None
                ),
                "read": bool(n.get('read')),
                "timestamp": _safe_iso(n.get('timestamp')),
            })
        unread = sum(1 for i in items if not i['read'])
        return json_response({"messages": items, "unread_count": unread}, 200)

    except Exception as e:
        logger.error(f"Error fetching doctor messages: {e}", exc_info=True)
        return json_response({"error": str(e)}, 500)


@router.post("/messages/{notification_id}/read", name="doctor.mark_message_read")
def mark_message_read(notification_id: str):
    """Mark one inbox notification as read."""
    try:
        ok = messages_repo.mark_notification_read(notification_id)
        return json_response({"status": "success" if ok else "not_found"}, 200 if ok else 404)
    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.post("/message", name="doctor.send_message")
def send_message(data: dict = Body(None)):
    """Send message to a mother via Telegram."""
    try:
        data = data or {}

        required_fields = ['doctor_id', 'mother_id', 'message']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return json_response({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }, 400)

        doctor_id = data['doctor_id']
        mother_id = data['mother_id']
        message_text = data['message']

        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return json_response({
                "error": "Doctor not found"
            }, 404)

        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return json_response({
                "error": "Mother not found"
            }, 404)

        telegram_chat_id = mother.get('telegram_chat_id')
        if not telegram_chat_id:
            return json_response({
                "error": "Mother does not have Telegram configured",
                "details": "Mother must register via Telegram bot first"
            }, 400)

        # Format message - simple, actionable, no medical jargon
        formatted_message = f"""
Message from Dr. {doctor.get('name')}

{message_text}

If you have questions, contact your ASHA worker.
"""

        telegram_sent = False
        telegram_error = None
        telegram_message_id = None

        try:
            result = telegram_service.send_message(telegram_chat_id, formatted_message)
            if result and result.get('ok'):
                telegram_sent = True
                telegram_message_id = result.get('result', {}).get('message_id')
        except Exception as telegram_err:
            logger.error(f"Telegram send failed: {telegram_err}")
            telegram_error = str(telegram_err)
            # Don't block workflow

        try:
            messages_repo.create({
                'mother_id': str(mother_id),
                'mother_name': mother.get('name'),
                'from_doctor': True,
                'doctor_name': doctor.get('name'),
                'message_type': 'doctor_message',
                'content': message_text,
                'message': message_text,
                'read': False,
            })
        except Exception as log_err:
            logger.error(f"Failed to log message: {log_err}")

        logger.info(f"Doctor {doctor.get('name')} sent message to {mother.get('name')}: {telegram_sent}")

        return json_response({
            "status": "success",
            "message": "Message sent successfully" if telegram_sent else "Message logged but delivery failed",
            "delivered": telegram_sent,
            "delivery_error": telegram_error,
            "mother_id": str(mother_id),
            "mother_name": mother.get('name'),
            "sent_at": datetime.now(timezone.utc).isoformat()
        }, 200 if telegram_sent else 207)  # 207 = Multi-Status (partial success)

    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        return json_response({
            "error": "Failed to send message",
            "details": str(e)
        }, 500)


@router.post("/review-document", name="doctor.review_document")
def review_document(data: dict = Body(None)):
    """Submit doctor's review of a medical document."""
    try:
        data = data or {}

        required = ['document_id', 'doctor_id', 'mother_id', 'notes']
        for field in required:
            if field not in data:
                return json_response({"error": f"Missing required field: {field}"}, 400)

        document_id = data['document_id']
        doctor_id = data['doctor_id']
        mother_id = data['mother_id']
        notes = data['notes']
        ai_overridden = data.get('ai_overridden', False)
        corrected_analysis = data.get('corrected_analysis')
        notify_to = data.get('notify_to', [])

        document = documents_repo.get_by_id(document_id)
        if not document:
            return json_response({"error": "Document not found"}, 404)

        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return json_response({"error": "Doctor not found"}, 404)

        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return json_response({"error": "Mother not found"}, 404)

        review_data = {
            "reviewed_at": datetime.now(timezone.utc),
            "reviewed_by_doctor_id": str(doctor_id),
            "doctor_name": doctor.get('name'),
            "notes": notes,
            "ai_overridden": ai_overridden,
            "notification_sent_to": notify_to
        }

        if ai_overridden and corrected_analysis:
            review_data['corrected_analysis'] = corrected_analysis

        documents_repo.add_doctor_review(document_id, review_data)

        logger.info(f"[DOCTOR REVIEW] Document {document_id} reviewed by {doctor.get('name')}")

        notifications_sent = []

        if 'asha' in notify_to or 'both' in notify_to:
            asha_id = mother.get('assigned_asha_id')
            if asha_id:
                message_text = f"""Doctor Review: Document Analysis for {mother.get('name')}.
Doctor's Notes: {notes}

Document: {document.get('file_metadata', {}).get('original_filename', 'Medical Document')}
View full details in the portal.
"""

                message_data = {
                    "mother_id": str(mother_id),
                    "mother_name": mother.get('name'),
                    "from_doctor": True,
                    "doctor_name": doctor.get('name'),
                    "to_asha_id": str(asha_id),
                    "message_type": "doctor_review",
                    "content": message_text,
                    "message": message_text,
                    "read": False,
                    "document_id": str(document_id),
                }
                messages_repo.create(message_data)
                notifications_sent.append('ASHA Portal')

                logger.info(f"[DOCTOR REVIEW] ASHA notification created")

        if 'mother' in notify_to or 'both' in notify_to:
            telegram_chat_id = mother.get('telegram_chat_id')

            if telegram_chat_id:
                telegram_message = f"""👨‍⚕️ *Doctor's Review*

Your medical document has been reviewed:

📄 *Document:* {document.get('file_metadata', {}).get('original_filename', 'Medical Report')}

*Doctor's Notes:*
{notes}

{'⚠️ *Important:* The doctor has provided corrected analysis. Please consult with your doctor for details.' if ai_overridden else ''}

If you have questions, please contact your ASHA worker or doctor.
"""

                try:
                    telegram_service.send_message(telegram_chat_id, telegram_message)
                    notifications_sent.append('Mother (Telegram)')

                    message_data = {
                        "mother_id": str(mother_id),
                        "mother_name": mother.get('name'),
                        "from_doctor": True,
                        "doctor_name": doctor.get('name'),
                        "message_type": "doctor_review_mother",
                        "content": notes,
                        "message": notes,
                        "read": False,
                        "document_id": str(document_id),
                    }
                    messages_repo.create(message_data)

                    logger.info(f"[DOCTOR REVIEW] Telegram sent to mother")

                except Exception as telegram_error:
                    logger.error(f"[DOCTOR REVIEW] Telegram failed: {telegram_error}")
                    notifications_sent.append('Mother (Telegram - Failed)')
            else:
                logger.warning(f"[DOCTOR REVIEW] Mother has no Telegram chat ID")
                notifications_sent.append('Mother (No Telegram)')

        return json_response({
            "success": True,
            "message": "Document review submitted successfully",
            "document_id": document_id,
            "notifications_sent": notifications_sent,
            "ai_overridden": ai_overridden
        }, 200)

    except Exception as e:
        logger.error(f"Error submitting document review: {e}", exc_info=True)
        return json_response({
            "error": "Failed to submit review",
            "details": str(e)
        }, 500)
