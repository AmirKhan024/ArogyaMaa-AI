"""
AI-Driven Telegram Alerts

Send risk-based alerts to mother, ASHA worker, and doctor based on AI evaluation.
"""

from flask import current_app
from app.services import telegram_service
from app.repositories import messages_repo, mothers_repo, asha_repo, doctors_repo


def send_ai_alerts(assessment_id, mother_id, ai_evaluation, mother_data, asha_data):
    """
    Send Telegram alerts based on AI evaluation risk level.
    
    Risk-based routing:
    - LOW: Reassurance to mother only
    - MODERATE: Guidance to mother + notify ASHA
    - HIGH/CRITICAL: Urgent alert to mother + ASHA + doctor (if requires_doctor_review)
    
    Args:
        assessment_id: Assessment ObjectId (for logging)
        mother_id: Mother ObjectId
        ai_evaluation: AI evaluation dict from assessments.ai_evaluation
        mother_data: Mother profile dict
        asha_data: ASHA worker profile dict
    
    Returns:
        dict: Status of sent messages
    """
    if not ai_evaluation:
        current_app.logger.warning(f"[ALERTS] No AI evaluation for assessment {assessment_id}")
        return {"status": "no_ai_evaluation"}
    
    risk_category = ai_evaluation.get('risk_category', 'MODERATE')
    requires_doctor_review = ai_evaluation.get('requires_doctor_review', False)
    
    current_app.logger.info(
        f"[ALERTS] Sending alerts for assessment {assessment_id}: "
        f"Risk={risk_category}, Doctor Review={requires_doctor_review}"
    )
    
    results = {
        "risk_category": risk_category,
        "mother_alert": None,
        "asha_alert": None,
        "doctor_alert": None
    }
    
    # Extract messages from Communication Agent output
    messages = _extract_ai_messages(ai_evaluation)
    
    # Send to mother (all risk levels)
    mother_msg = _get_message_for_recipient(messages, "mother", risk_category, mother_data)
    if mother_msg:
        results["mother_alert"] = _send_to_mother(
            mother_data, 
            mother_msg, 
            assessment_id,
            risk_category
        )
    
    # Send to ASHA for MODERATE, HIGH, CRITICAL
    if risk_category in ["MODERATE", "HIGH", "CRITICAL"]:
        asha_msg = _get_message_for_recipient(messages, "asha_worker", risk_category, mother_data, asha_data)
        if asha_msg:
            results["asha_alert"] = _send_to_asha(
                asha_data,
                asha_msg,
                mother_data,
                assessment_id,
                risk_category
            )
    
    # Send to doctor for HIGH/CRITICAL with doctor review required
    if risk_category in ["HIGH", "CRITICAL"] and requires_doctor_review:
        # Get assigned doctor
        doctor_id = mother_data.get('assigned_doctor_id')
        if doctor_id:
            doctor_data = doctors_repo.get_by_id(doctor_id)
            if doctor_data:
                doctor_msg = _get_message_for_recipient(messages, "doctor", risk_category, mother_data, asha_data)
                if doctor_msg:
                    results["doctor_alert"] = _send_to_doctor(
                        doctor_data,
                        doctor_msg,
                        mother_data,
                        assessment_id,
                        risk_category
                    )
    
    return results


def _extract_ai_messages(ai_evaluation):
    """
    Extract messages from Communication Agent output.
    
    Returns:
        dict: Messages for mother, ASHA, doctor
    """
    comm_output = ai_evaluation.get('agent_outputs', {}).get('communication', {})
    
    # NEW: Return dict with separate messages (Pydantic format)
    return {
        'mother': comm_output.get('message_for_mother', comm_output.get('mother_message', '')),
        'asha_worker': comm_output.get('message_for_asha', comm_output.get('asha_message', '')),
        'doctor': comm_output.get('message_for_doctor', comm_output.get('doctor_message', ''))
    }


def _get_message_for_recipient(ai_messages, recipient, risk_category, mother_data, worker_data=None):
    """
    Get message for specific recipient from AI output or fallback template.
    
    Args:
        ai_messages: Dict of messages (mother, asha_worker, doctor)
        recipient: 'mother', 'asha_worker', or 'doctor'
        risk_category: Risk level
        mother_data: Mother profile
        worker_data: ASHA or doctor profile (optional)
    
    Returns:
        str: Message text
    """
    # FIXED: ai_messages is now a dict, not a list
    if isinstance(ai_messages, dict):
        message = ai_messages.get(recipient, '')
        if message:
            return message
    
    # Fallback to template
    return _get_template_message(recipient, risk_category, mother_data, worker_data)


def _get_template_message(recipient, risk_category, mother_data, worker_data=None):
    """
    Generate template message if AI communication output is missing.
    
    Args:
        recipient: 'mother', 'asha_worker', or 'doctor'
        risk_category: Risk level
        mother_data: Mother profile
        worker_data: ASHA or doctor profile
    
    Returns:
        str: Template message
    """
    mother_name = mother_data.get('name', 'Mother')
    
    if recipient == "mother":
        templates = {
            "LOW": f"नमस्ते {mother_name} जी,\n\nआपकी स्वास्थ्य जांच पूरी हो गई है। सब कुछ ठीक है। अगली जांच के लिए समय पर आएं।\n\n- ArogyaMaa",
            
            "MODERATE": f"नमस्ते {mother_name} जी,\n\nआपकी जांच में कुछ बातों पर ध्यान देने की जरूरत है। कृपया 3-5 दिन में डॉक्टर से मिलें। आशा बहन आपकी मदद करेंगी।\n\n- ArogyaMaa",
            
            "HIGH": f"⚠️ {mother_name} जी,\n\nआपकी स्वास्थ्य जांच में कुछ गंभीर बातें मिली हैं। कृपया 24 घंटे के अंदर डॉक्टर से संपर्क करें। आशा बहन जल्द ही आपसे मिलेंगी।\n\n- ArogyaMaa",
            
            "CRITICAL": f"🚨 {mother_name} जी - तत्काल ध्यान दें\n\nआपकी स्वास्थ्य स्थिति गंभीर है। कृपया तुरंत अस्पताल जाएं या डॉक्टर को बुलाएं। आशा बहन और डॉक्टर को सूचित कर दिया गया है।\n\n- ArogyaMaa"
        }
        return templates.get(risk_category, templates["MODERATE"])
    
    elif recipient == "asha_worker":
        worker_name = worker_data.get('name', 'ASHA') if worker_data else 'ASHA'
        
        templates = {
            "MODERATE": f"ALERT: {mother_name}\n\nRisk: MODERATE\nAction: Schedule doctor visit within 3-5 days\nMonitor for symptom changes\n\n- ArogyaMaa AI",
            
            "HIGH": f"⚠️ URGENT: {mother_name}\n\nRisk: HIGH\nAction Required: Doctor visit within 24 hours\nPlease follow up immediately\n\n- ArogyaMaa AI",
            
            "CRITICAL": f"🚨 CRITICAL: {mother_name}\n\nRisk: CRITICAL\nAction: IMMEDIATE referral to hospital\nDoctor has been notified\nContact mother NOW\n\n- ArogyaMaa AI"
        }
        return templates.get(risk_category, templates["MODERATE"])
    
    elif recipient == "doctor":
        templates = {
            "HIGH": f"New Assessment - {mother_name}\n\nRisk: HIGH\nAI Confidence: Requires review\nAction: Review assessment within 24-48h\n\nView in dashboard: /doctor/assessments?mother_id=...\n\n- ArogyaMaa AI",
            
            "CRITICAL": f"🚨 URGENT - {mother_name}\n\nRisk: CRITICAL\nImmediate doctor review required\nASHA worker notified\n\nView assessment now: /doctor/assessments?mother_id=...\n\n- ArogyaMaa AI"
        }
        return templates.get(risk_category, templates["HIGH"])
    
    return f"Health assessment update for {mother_name}"


def _send_to_mother(mother_data, message_text, assessment_id, risk_category):
    """
    Send alert to mother via Telegram and log in messages collection.
    
    Returns:
        dict: Status of send operation
    """
    mother_id = mother_data.get('_id')
    telegram_chat_id = mother_data.get('telegram_chat_id')
    
    if not telegram_chat_id:
        current_app.logger.warning(f"[ALERTS] Mother {mother_id} has no telegram_chat_id")
        return {"status": "no_telegram_chat_id"}
    
    result = {"status": "failed", "telegram_sent": False, "logged": False}
    
    try:
        # Send via Telegram
        telegram_response = telegram_service.send_message(telegram_chat_id, message_text)
        
        if telegram_response and telegram_response.get('ok'):
            result["telegram_sent"] = True
            result["status"] = "sent"
            telegram_msg_id = telegram_response.get('result', {}).get('message_id')
            
            # Log in messages collection
            message_data = {
                'sender_type': 'ai',
                'sender_name': 'ArogyaMaa AI',
                'text': message_text,
                'telegram_message_id': telegram_msg_id,
                'is_alert': True,
                'alert_type': f'ai_risk_{risk_category.lower()}',
                'related_assessment_id': str(assessment_id)
            }
            
            logged = messages_repo.add_message(mother_id, message_data)
            result["logged"] = logged
            
            current_app.logger.info(f"[ALERTS] ✓ Sent to mother {mother_id}: {risk_category}")
        else:
            current_app.logger.error(f"[ALERTS] Telegram API error for mother {mother_id}")
    
    except Exception as e:
        current_app.logger.error(f"[ALERTS] Error sending to mother {mother_id}: {e}", exc_info=True)
    
    return result


def _send_to_asha(asha_data, message_text, mother_data, assessment_id, risk_category):
    """
    Send alert to ASHA worker via Telegram.
    
    Returns:
        dict: Status of send operation
    """
    asha_id = asha_data.get('_id')
    telegram_chat_id = asha_data.get('telegram_chat_id')
    
    if not telegram_chat_id:
        current_app.logger.warning(f"[ALERTS] ASHA {asha_id} has no telegram_chat_id")
        return {"status": "no_telegram_chat_id"}
    
    result = {"status": "failed", "telegram_sent": False}
    
    try:
        # Send via Telegram
        telegram_response = telegram_service.send_message(telegram_chat_id, message_text)
        
        if telegram_response and telegram_response.get('ok'):
            result["telegram_sent"] = True
            result["status"] = "sent"
            current_app.logger.info(f"[ALERTS] ✓ Sent to ASHA {asha_id}: {risk_category}")
        else:
            current_app.logger.error(f"[ALERTS] Telegram API error for ASHA {asha_id}")
    
    except Exception as e:
        current_app.logger.error(f"[ALERTS] Error sending to ASHA {asha_id}: {e}", exc_info=True)
    
    return result


def _send_to_doctor(doctor_data, message_text, mother_data, assessment_id, risk_category):
    """
    Send alert to doctor via Telegram.
    
    Returns:
        dict: Status of send operation
    """
    doctor_id = doctor_data.get('_id')
    telegram_chat_id = doctor_data.get('telegram_chat_id')
    
    if not telegram_chat_id:
        current_app.logger.warning(f"[ALERTS] Doctor {doctor_id} has no telegram_chat_id")
        return {"status": "no_telegram_chat_id"}
    
    result = {"status": "failed", "telegram_sent": False}
    
    try:
        # Send via Telegram
        telegram_response = telegram_service.send_message(telegram_chat_id, message_text)
        
        if telegram_response and telegram_response.get('ok'):
            result["telegram_sent"] = True
            result["status"] = "sent"
            current_app.logger.info(f"[ALERTS] ✓ Sent to doctor {doctor_id}: {risk_category}")
        else:
            current_app.logger.error(f"[ALERTS] Telegram API error for doctor {doctor_id}")
    
    except Exception as e:
        current_app.logger.error(f"[ALERTS] Error sending to doctor {doctor_id}: {e}", exc_info=True)
    
    return result
