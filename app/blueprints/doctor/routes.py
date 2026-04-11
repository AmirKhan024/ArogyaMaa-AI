"""
Doctor Blueprint

Handles doctor dashboard APIs.
Doctors review assessments and enter consultation details.

URL Prefix: /doctor
"""

from flask import Blueprint, request, jsonify, current_app
from bson import ObjectId
from datetime import datetime
from app.repositories import (
    mothers_repo, 
    doctors_repo, 
    assessments_repo, 
    consultations_repo,
    messages_repo,
    documents_repo
)
from app.services import telegram_service

doctor_bp = Blueprint('doctor', __name__)


def _safe_iso(value):
    """Return ISO-format string for datetime or plain string dates; None if absent."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


@doctor_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Doctor service"""
    return jsonify({
        "service": "doctor",
        "status": "active"
    }), 200


@doctor_bp.route('/mothers', methods=['GET'])
def get_mothers():
    """
    Get list of mothers assigned to a doctor.
    
    Query params:
    - doctor_id: Doctor ID (required)
    
    Returns:
    - List of assigned mothers with latest assessment info
    """
    try:
        # Get doctor ID from query params
        doctor_id = request.args.get('doctor_id')
        
        if not doctor_id:
            return jsonify({
                "error": "doctor_id parameter is required"
            }), 400
        
        # Verify doctor exists
        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return jsonify({
                "error": "Doctor not found"
            }), 404
        
        # Get assigned mothers
        mothers = mothers_repo.list_by_doctor(doctor_id)
        
        # Format response with latest assessment info
        mothers_list = []
        for mother in mothers:
            # Get latest assessment
            latest_assessment = assessments_repo.get_latest_for_mother(mother['_id'])

            pregnancy = mother.get('current_pregnancy') or {}

            # Resolve ASHA worker name for this mother
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

            # Add latest assessment info if exists
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

                # Count pending reviews
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

        return jsonify({
            "doctor_id": doctor_id,
            "doctor_name": doctor.get('name'),
            "total_mothers": len(mothers_list),
            "mothers": mothers_list
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching mothers for doctor: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch mothers",
            "details": str(e)
        }), 500


@doctor_bp.route('/assessments', methods=['GET'])
def get_assessments():
    """
    Get assessment history for a specific mother OR pending assessments for a doctor.
    
    Query params:
    - mother_id: Mother ID (to get history for one mother)
    - doctor_id: Doctor ID (to get all pending reviews for this doctor)
    - limit: Number of assessments to return (optional, default: 50)
    
    Returns:
    - List of assessments with AI evaluations and basic info
    """
    try:
        mother_id = request.args.get('mother_id')
        doctor_id = request.args.get('doctor_id')
        limit = request.args.get('limit', default=50, type=int)
        
        assessments_list = []
        
        if mother_id:
            # Case 1: Get history for a specific mother
            mother = mothers_repo.get_by_id(mother_id)
            if not mother:
                return jsonify({"error": "Mother not found"}), 404
            
            # Use specific mother name for all assessments here
            common_mother_name = mother.get('name', 'Unknown')
            assessments = assessments_repo.list_by_mother(mother_id, limit=limit)
            
            # Context for ASHA name resolution
            from app.repositories import asha_repo
            
            for assessment in assessments:
                inner_asha_id = assessment.get('asha_id')
                inner_asha_name = 'ASHA Worker'
                if inner_asha_id:
                    asha_worker = asha_repo.get_by_id(str(inner_asha_id))
                    if asha_worker:
                        inner_asha_name = asha_worker.get('name', 'ASHA Worker')
                
                assessments_list.append(_format_as_s_res(assessment, common_mother_name, inner_asha_name))
                
            return jsonify({
                "mother_id": mother_id,
                "mother_name": common_mother_name,
                "total_assessments": len(assessments_list),
                "assessments": assessments_list
            }), 200

        elif doctor_id:
            # Case 2: Get all pending assessments for a doctor (Dashboard view)
            assessments = assessments_repo.list_pending_doctor_review(doctor_id, limit=limit)
            
            from app.repositories import asha_repo
            
            for assessment in assessments:
                # Need to resolve mother name for each
                m_id = assessment.get('mother_id')
                m_name = 'Unknown'
                if m_id:
                    m_obj = mothers_repo.get_by_id(str(m_id))
                    if m_obj:
                        m_name = m_obj.get('name', 'Unknown')
                
                # Need to resolve ASHA name for each
                a_id = assessment.get('asha_id')
                a_name = 'ASHA Worker'
                if a_id:
                    a_obj = asha_repo.get_by_id(str(a_id))
                    if a_obj:
                        a_name = a_obj.get('name', 'ASHA Worker')
                
                assessments_list.append(_format_as_s_res(assessment, m_name, a_name))
                
            return jsonify({
                "doctor_id": doctor_id,
                "total_assessments": len(assessments_list),
                "assessments": assessments_list
            }), 200
            
        else:
            return jsonify({
                "error": "Either mother_id or doctor_id parameter is required"
            }), 400
            
    except Exception as e:
        current_app.logger.error(f"Error fetching assessments: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch assessments",
            "details": str(e)
        }), 500


def _format_as_s_res(assessment, mother_name, asha_name):
    """Internal helper to format assessment data for list views"""
    ai_eval = assessment.get('ai_evaluation', {})
    
    # Get consultation details if reviewed
    doctor_consultation = None
    if assessment.get('reviewed_by_doctor') and assessment.get('consultation_id'):
        from app.repositories import consultations_repo
        consultation = consultations_repo.get_by_id(assessment.get('consultation_id'))
        if consultation:
            # Basic consultation info
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
            "recommended_actions": ai_eval.get('recommended_actions', [])
        } if ai_eval else None,
        "doctor_reviewed": assessment.get('reviewed_by_doctor', False),
        "doctor_consultation": doctor_consultation
    }


@doctor_bp.route('/assessment/<assessment_id>', methods=['GET'])
def get_assessment_by_id(assessment_id):
    """
    Get a single assessment by ID with full details including consultation.
    
    Path params:
    - assessment_id: Assessment ID
    
    Query params:
    - doctor_id: Doctor ID (optional, for validation)
    
    Returns:
    - Assessment details with AI evaluation and consultation
    """
    try:
        # Get assessment
        assessment = assessments_repo.get_by_id(assessment_id)
        if not assessment:
            return jsonify({
                "error": "Assessment not found"
            }), 404
        
        # Get mother details
        mother = mothers_repo.get_by_id(assessment['mother_id'])
        
        # Get ASHA worker name
        asha_name = 'ASHA Worker'
        asha_id = assessment.get('asha_id')
        if asha_id:
            from app.repositories import asha_repo
            asha_worker = asha_repo.get_by_id(asha_id)
            if asha_worker:
                asha_name = asha_worker.get('name', 'ASHA Worker')
        
        # Get AI evaluation
        ai_eval = assessment.get('ai_evaluation', {})
        
        # Get consultation details if reviewed
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
        
        return jsonify(assessment_data), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching assessment: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch assessment",
            "details": str(e)
        }), 500


@doctor_bp.route('/consultation', methods=['POST'])
def submit_consultation():
    """
    Submit consultation details for an assessment.
    
    Expected payload:
    {
        "assessment_id": "ObjectId",
        "doctor_id": "ObjectId",
        "diagnosis": "string",
        "clinical_observations": "string",
        "updated_vitals": {
            "bp_systolic": number (optional),
            "bp_diastolic": number (optional),
            ...
        },
        "treatment_plan": {
            "medications": [
                {
                    "name": "string",
                    "dosage": "string",
                    "frequency": "string",
                    "duration_days": number
                }
            ],
            "nutrition_plan": "string",
            "activity_restrictions": "string",
            "follow_up_instructions": "string"
        },
        "next_visit_date": "ISO date string",
        "overrides_ai_assessment": boolean (optional),
        "doctor_risk_assessment": "string (LOW/MODERATE/HIGH)" (optional),
        "override_reason": "string" (optional),
        "consultation_notes": "string" (optional)
    }
    
    Returns:
    - Created consultation with ID
    - Updates assessment as reviewed
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['assessment_id', 'doctor_id', 'diagnosis']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        assessment_id = data['assessment_id']
        doctor_id = data['doctor_id']
        
        # Verify assessment exists
        assessment = assessments_repo.get_by_id(assessment_id)
        if not assessment:
            return jsonify({
                "error": "Assessment not found"
            }), 404
        
        # Verify doctor exists
        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return jsonify({
                "error": "Doctor not found"
            }), 404
        
        # Get mother details
        mother_id = assessment['mother_id']
        mother = mothers_repo.get_by_id(mother_id)
        
        # Parse next_visit_date if provided
        next_visit_date = None
        if data.get('next_visit_date'):
            try:
                next_visit_date = datetime.fromisoformat(data['next_visit_date'].replace('Z', '+00:00'))
            except:
                next_visit_date = None
        
        # Create consultation record
        consultation_data = {
            'assessment_id': ObjectId(assessment_id),
            'mother_id': mother_id,
            'doctor_id': ObjectId(doctor_id),
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
        
        # Mark assessment as reviewed
        assessments_repo.mark_as_reviewed(assessment_id, consultation_id, doctor_id)
        
        # Update doctor stats
        is_high_risk = assessment.get('ai_evaluation', {}).get('risk_category') == 'HIGH'
        doctors_repo.increment_consultation_count(doctor_id, is_high_risk=is_high_risk)
        
        # Prepare detailed message for mother (includes diagnosis, treatment, next visit)
        # Parse treatment plan (can be string or dict)
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
        
        # Send message to mother via Telegram (with error handling)
        telegram_sent = False
        telegram_error = None
        if mother.get('telegram_chat_id'):
            try:
                telegram_service.send_message(mother['telegram_chat_id'], mother_message)
                telegram_sent = True
            except Exception as telegram_err:
                current_app.logger.error(f"Telegram send failed: {telegram_err}")
                telegram_error = str(telegram_err)
                # Don't block workflow if Telegram fails
            
            # Log message in messages collection with delivery status
            try:
                messages_repo.create({
                    'mother_id': mother_id,
                    'assessment_id': ObjectId(assessment_id),
                    'consultation_id': consultation_id,
                    'sender_type': 'doctor',
                    'sender_id': ObjectId(doctor_id),
                    'sender_name': doctor.get('name'),
                    'recipient_type': 'mother',
                    'recipient_id': mother_id,
                    'message_text': mother_message,
                    'delivery_status': 'sent' if telegram_sent else 'failed',
                    'delivery_error': telegram_error,
                    'created_at': datetime.utcnow()
                })
            except Exception as log_err:
                current_app.logger.error(f"Failed to log message: {log_err}")
        
        return jsonify({
            "status": "success",
            "message": "Consultation submitted successfully",
            "consultation_id": str(consultation_id),
            "assessment_marked_reviewed": True,
            "mother_notified": telegram_sent,
            "notification_error": telegram_error
        }), 201
    
    except Exception as e:
        current_app.logger.error(f"Error submitting consultation: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to submit consultation",
            "details": str(e)
        }), 500


@doctor_bp.route('/message', methods=['POST'])
def send_message():
    """
    Send message to a mother via Telegram.
    
    Expected payload:
    {
        "doctor_id": "ObjectId",
        "mother_id": "ObjectId",
        "message": "string"
    }
    
    Returns:
    - Success status
    - Message delivery confirmation
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['doctor_id', 'mother_id', 'message']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        doctor_id = data['doctor_id']
        mother_id = data['mother_id']
        message_text = data['message']
        
        # Verify doctor exists
        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return jsonify({
                "error": "Doctor not found"
            }), 404
        
        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return jsonify({
                "error": "Mother not found"
            }), 404
        
        # Check if mother has Telegram chat ID
        telegram_chat_id = mother.get('telegram_chat_id')
        if not telegram_chat_id:
            return jsonify({
                "error": "Mother does not have Telegram configured",
                "details": "Mother must register via Telegram bot first"
            }), 400
        
        # Format message - simple, actionable, no medical jargon
        formatted_message = f"""
Message from Dr. {doctor.get('name')}

{message_text}

If you have questions, contact your ASHA worker.
"""
        
        # Send message via Telegram with error handling
        telegram_sent = False
        telegram_error = None
        telegram_message_id = None
        
        try:
            result = telegram_service.send_message(telegram_chat_id, formatted_message)
            if result and result.get('ok'):
                telegram_sent = True
                telegram_message_id = result.get('result', {}).get('message_id')
        except Exception as telegram_err:
            current_app.logger.error(f"Telegram send failed: {telegram_err}")
            telegram_error = str(telegram_err)
            # Don't block workflow
        
        # Log message in messages collection with delivery status
        try:
            messages_repo.create({
                'mother_id': ObjectId(mother_id),
                'sender_type': 'doctor',
                'sender_id': ObjectId(doctor_id),
                'sender_name': doctor.get('name'),
                'recipient_type': 'mother',
                'recipient_id': ObjectId(mother_id),
                'message_text': message_text,
                'delivery_status': 'sent' if telegram_sent else 'failed',
                'delivery_error': telegram_error,
                'telegram_message_id': telegram_message_id,
                'created_at': datetime.utcnow()
            })
        except Exception as log_err:
            current_app.logger.error(f"Failed to log message: {log_err}")
        
        current_app.logger.info(f"Doctor {doctor.get('name')} sent message to {mother.get('name')}: {telegram_sent}")
        
        return jsonify({
            "status": "success",
            "message": "Message sent successfully" if telegram_sent else "Message logged but delivery failed",
            "delivered": telegram_sent,
            "delivery_error": telegram_error,
            "mother_id": str(mother_id),
            "mother_name": mother.get('name'),
            "sent_at": datetime.utcnow().isoformat()
        }), 200 if telegram_sent else 207  # 207 = Multi-Status (partial success)
    
    except Exception as e:
        current_app.logger.error(f"Error sending message: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to send message",
            "details": str(e)
        }), 500


@doctor_bp.route('/review-document', methods=['POST'])
def review_document():
    """
    Submit doctor's review of a medical document.
    Can override AI analysis and send notifications to ASHA/Mother.
    
    POST body:
    {
        "document_id": "ObjectId",
        "doctor_id": "ObjectId",
        "mother_id": "ObjectId",
        "notes": "Doctor's clinical notes",
        "ai_overridden": boolean,
        "corrected_analysis": {  // Only if ai_overridden=true
            "key_findings": [],
            "abnormal_values": [],
            "clinical_summary": ""
        },
        "notify_to": ["asha", "mother"]  // or both
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['document_id', 'doctor_id', 'mother_id', 'notes']
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        document_id = data['document_id']
        doctor_id = data['doctor_id']
        mother_id = data['mother_id']
        notes = data['notes']
        ai_overridden = data.get('ai_overridden', False)
        corrected_analysis = data.get('corrected_analysis')
        notify_to = data.get('notify_to', [])
        
        # Verify document exists
        document = documents_repo.get_by_id(document_id)
        if not document:
            return jsonify({"error": "Document not found"}), 404
        
        # Verify doctor exists
        doctor = doctors_repo.get_by_id(doctor_id)
        if not doctor:
            return jsonify({"error": "Doctor not found"}), 404
        
        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return jsonify({"error": "Mother not found"}), 404
        
        # Create doctor review record
        review_data = {
            "reviewed_at": datetime.utcnow(),
            "reviewed_by_doctor_id": ObjectId(doctor_id),
            "doctor_name": doctor.get('name'),
            "notes": notes,
            "ai_overridden": ai_overridden,
            "notification_sent_to": notify_to
        }
        
        if ai_overridden and corrected_analysis:
            review_data['corrected_analysis'] = corrected_analysis
        
        # Update document with doctor review
        documents_repo.add_doctor_review(document_id, review_data)
        
        current_app.logger.info(f"[DOCTOR REVIEW] Document {document_id} reviewed by {doctor.get('name')}")
        
        # Send notifications
        notifications_sent = []
        
        if 'asha' in notify_to or 'both' in notify_to:
            # Get ASHA worker for this mother
            asha_id = mother.get('assigned_asha_id')
            if asha_id:
                # Create notification message for ASHA
                message_text = f"""Doctor Review: Document Analysis for {mother.get('name')}.
Doctor's Notes: {notes}

Document: {document.get('file_metadata', {}).get('original_filename', 'Medical Document')}
View full details in the portal.
"""
                
                # Save message to database
                message_data = {
                    "mother_id": ObjectId(mother_id),
                    "from_doctor": True,
                    "from_doctor_id": ObjectId(doctor_id),
                    "to_asha": True,
                    "to_asha_id": asha_id,
                    "message": message_text,
                    "timestamp": datetime.utcnow(),
                    "document_id": ObjectId(document_id)
                }
                messages_repo.create(message_data)
                notifications_sent.append('ASHA Portal')
                
                current_app.logger.info(f"[DOCTOR REVIEW] ASHA notification created")
        
        if 'mother' in notify_to or 'both' in notify_to:
            # Send Telegram message to mother
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
                    
                    # Log message in database
                    message_data = {
                        "mother_id": ObjectId(mother_id),
                        "from_doctor": True,
                        "from_doctor_id": ObjectId(doctor_id),
                        "to_mother": True,
                        "message": notes,
                        "timestamp": datetime.utcnow(),
                        "telegram_sent": True,
                        "document_id": ObjectId(document_id)
                    }
                    messages_repo.create(message_data)
                    
                    current_app.logger.info(f"[DOCTOR REVIEW] Telegram sent to mother")
                    
                except Exception as telegram_error:
                    current_app.logger.error(f"[DOCTOR REVIEW] Telegram failed: {telegram_error}")
                    notifications_sent.append('Mother (Telegram - Failed)')
            else:
                current_app.logger.warning(f"[DOCTOR REVIEW] Mother has no Telegram chat ID")
                notifications_sent.append('Mother (No Telegram)')
        
        return jsonify({
            "success": True,
            "message": "Document review submitted successfully",
            "document_id": document_id,
            "notifications_sent": notifications_sent,
            "ai_overridden": ai_overridden
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error submitting document review: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to submit review",
            "details": str(e)
        }), 500
