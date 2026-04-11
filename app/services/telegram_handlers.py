"""
Telegram Bot Command Handlers - Batch-3 Menu Experience

Handles all Telegram bot commands and message processing.
Mothers interact through inline keyboard menus.
"""

import os
import asyncio
from flask import current_app
from app.repositories import mothers_repo, messages_repo, assessments_repo, consultations_repo, registration_repo
from app.services import telegram_service
from app.ai.nutrition_advisor import is_nutrition_query, generate_nutrition_recommendation
from bson import ObjectId
from datetime import datetime


# ==================== AI REGISTRATION SETUP ====================

_reg_engine = None
_voice_processor = None


def _get_registration_engine():
    """Lazy-initialize the AI registration engine."""
    global _reg_engine
    if _reg_engine is None:
        groq_key = current_app.config.get('GROQ_API_KEY')
        if groq_key:
            from app.ai.registration.assistant import AIAssistant
            from app.ai.registration.engine import RegistrationEngine
            assistant = AIAssistant(groq_api_key=groq_key)
            _reg_engine = RegistrationEngine(assistant)
    return _reg_engine


def _get_voice_processor():
    """Lazy-initialize the voice processor."""
    global _voice_processor
    if _voice_processor is None:
        groq_key = current_app.config.get('GROQ_API_KEY')
        if groq_key:
            from app.ai.registration.voice_processor import VoiceProcessor
            _voice_processor = VoiceProcessor(groq_api_key=groq_key)
    return _voice_processor


def _get_keyboard_json(ui_details):
    """Convert registration UI details to Telegram API keyboard JSON."""
    ui_type = ui_details.get('type', 'text')
    options = ui_details.get('options', [])

    if ui_type in ['binary', 'choice'] and options:
        keyboard = [[opt] for opt in options]
        return {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True}
    elif ui_type == 'contact':
        return {
            "keyboard": [[{"text": "📱 Share Phone Number / अपना फोन नंबर साझा करें", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
    return {"remove_keyboard": True}


def _run_tts_and_send(chat_id, text, session):
    """Generate TTS voice and send it (runs async TTS in sync Flask context)."""
    try:
        vp = _get_voice_processor()
        if not vp:
            return

        user_lang = session.get('preferred_language', 'Hindi')

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        voice_path = loop.run_until_complete(vp.text_to_audio(text, lang=user_lang))
        loop.close()

        if voice_path and os.path.exists(voice_path):
            telegram_service.send_voice(chat_id, voice_path)
            os.remove(voice_path)
    except Exception as e:
        current_app.logger.error(f"TTS failed for chat {chat_id}: {e}")


def handle_start_command(chat_id, user_info):
    """
    Handle /start command - Show main menu with inline keyboard.
    
    Flow:
    1. Check if mother exists (by telegram_chat_id)
    2. If exists → Show main menu
    3. If not → Create profile → Show main menu
    
    Args:
        chat_id: Telegram chat ID
        user_info: Telegram user information from update
    
    Returns:
        dict: Response data with mother_id and status
    """
    # Check if mother already exists
    existing_mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if existing_mother:
        # Existing mother - show menu
        _send_main_menu(chat_id, existing_mother['name'])
        
        # Log interaction
        messages_repo.add_message(existing_mother['_id'], {
            'sender_type': 'system',
            'sender_name': 'ArogyaMaa System',
            'text': 'Mother opened main menu (/start)'
        })
        
        return {
            'status': 'existing_user',
            'mother_id': str(existing_mother['_id']),
            'name': existing_mother['name']
        }
    
    else:
        # New mother - create profile
        first_name = user_info.get('first_name', 'Mother')
        last_name = user_info.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip()
        username = user_info.get('username', '')
        
        # Create minimal mother profile
        mother_id = mothers_repo.create({
            'name': full_name,
            'age': None,
            'phone': None,
            'telegram_chat_id': str(chat_id),
            'telegram_username': username,
            'assigned_asha_id': None,
            'assigned_doctor_id': None,
            'medical_history': {},
            'current_pregnancy': {},
            'address': {}
        })
        
        # Create message thread
        messages_repo.create_thread(mother_id)
        
        # Send welcome + menu
        welcome_msg = f"""
🌸 <b>Welcome to ArogyaMaa, {full_name}!</b>

ArogyaMaa is your maternal health companion throughout your pregnancy journey.

Please choose an option from the menu below:
"""
        telegram_service.send_message(chat_id, welcome_msg)
        _send_main_menu(chat_id, full_name)
        
        # Log registration
        messages_repo.add_message(mother_id, {
            'sender_type': 'system',
            'sender_name': 'ArogyaMaa System',
            'text': f'New mother registered: {full_name}'
        })
        
        current_app.logger.info(f"New mother registered: {full_name} (chat_id: {chat_id})")
        
        return {
            'status': 'new_user',
            'mother_id': str(mother_id),
            'name': full_name
        }


def _send_main_menu(chat_id, name):
    """Send main menu with inline keyboard buttons."""
    message = f"""
<b>ArogyaMaa Main Menu</b>

What would you like to do, {name}?

💬 <b>Tip:</b> You can also just type a message to send it directly to your doctor and ASHA worker!
"""
    
    # Inline keyboard with 6 options
    reply_markup = {
        'inline_keyboard': [
            [{'text': '🩺 Health Summary', 'callback_data': 'menu_health_summary'}],
            [{'text': '📄 Upload Documents', 'callback_data': 'menu_upload_docs'}],
            [{'text': '🚨 Alerts', 'callback_data': 'menu_alerts'}],
            [{'text': '👩‍⚕️ Doctor Messages', 'callback_data': 'menu_doctor_messages'}],
            [{'text': '💬 Send Message', 'callback_data': 'menu_send_message'}],
            [{'text': '📝 Register', 'callback_data': 'menu_register'}]
        ]
    }
    
    telegram_service.send_formatted_message(chat_id, message, reply_markup)


def handle_callback_query(callback_query):
    """
    Handle inline keyboard button callbacks.
    
    Routes callback_data to appropriate handler:
    - menu_health_summary → Show health summary
    - menu_upload_docs → Show upload instructions
    - menu_alerts → Show alerts
    - menu_doctor_messages → Show doctor messages
    
    Args:
        callback_query: Telegram callback_query object
    
    Returns:
        dict: Response status
    """
    chat_id = callback_query.get('from', {}).get('id')
    callback_data = callback_query.get('data')
    
    if not chat_id or not callback_data:
        return {'status': 'invalid_callback'}
    
    # Answer callback to remove loading state
    _answer_callback_query(callback_query['id'])
    
    # Route to appropriate handler
    if callback_data == 'menu_health_summary':
        return handle_health_summary(chat_id)
    elif callback_data == 'menu_upload_docs':
        return handle_upload_docs_menu(chat_id)
    elif callback_data == 'menu_alerts':
        return handle_alerts_menu(chat_id)
    elif callback_data == 'menu_doctor_messages':
        return handle_doctor_messages(chat_id)
    elif callback_data == 'menu_send_message':
        return handle_send_message_menu(chat_id)
    elif callback_data == 'menu_register':
        return handle_registration_start(chat_id)
    else:
        telegram_service.send_message(chat_id, "Unknown option. Use /start to see the menu.")
        return {'status': 'unknown_callback'}


def handle_health_summary(chat_id):
    """
    Handle 🩺 Health Summary button.
    
    Fetches and displays:
    - Latest assessment
    - AI risk summary
    - Doctor consultation (if reviewed)
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first.")
        return {'status': 'not_registered'}
    
    mother_id = mother['_id']
    
    # Fetch latest assessment
    assessments = assessments_repo.list_by_mother(mother_id, limit=1)
    
    if not assessments or len(assessments) == 0:
        message = """
📋 <b>Health Summary</b>

No health assessments yet.

Your ASHA worker will conduct regular health checks and enter vitals into the system.

Use /start to return to the main menu.
"""
        telegram_service.send_message(chat_id, message)
        return {'status': 'no_assessments'}
    
    assessment = assessments[0]
    ai_eval = assessment.get('ai_evaluation', {})
    
    # Build summary message
    risk_category = ai_eval.get('risk_category', 'UNKNOWN')
    risk_emoji = {'LOW': '🟢', 'MODERATE': '🟡', 'HIGH': '🟠', 'CRITICAL': '🔴'}.get(risk_category, '⚪')
    
    # Key vitals - intelligently handle multiple field name formats
    vitals = assessment.get('vitals', {})
    bp_systolic = vitals.get('bp_systolic', 'N/A')
    bp_diastolic = vitals.get('bp_diastolic', 'N/A')
    # Handle both 'weight' and 'weight_kg' field names, fallback to mother profile
    weight = vitals.get('weight') or vitals.get('weight_kg')
    if not weight:
        weight = mother.get('medical_history', {}).get('weight', 'N/A')
        
    # Handle both 'hemoglobin' and 'hemoglobin_g_dl' field names
    hemoglobin = vitals.get('hemoglobin') or vitals.get('hemoglobin_g_dl') or 'N/A'
    
    # Handle pulse/heart rate
    pulse = vitals.get('pulse') or vitals.get('heart_rate') or 'N/A'
    
    message = f"""
📋 <b>Your Health Summary</b>

{risk_emoji} <b>Risk Level:</b> {risk_category}

<b>Key Vitals:</b>
• Blood Pressure: {bp_systolic}/{bp_diastolic} mmHg
• Weight: {weight} kg
• Hemoglobin: {hemoglobin} g/dL
• Pulse/Heart Rate: {pulse} bpm

<b>AI Health Summary:</b>
"""
    
    # Add AI summary (non-alarming) - FIXED: use correct field names
    comm_output = ai_eval.get('agent_outputs', {}).get('communication', {})
    # Try multiple field name variations (backwards compatibility)
    mother_msg = (comm_output.get('message_for_mother') or 
                  comm_output.get('mother_message') or 
                  '')
    if mother_msg:
        message += f"{mother_msg}\n\n"
    else:
        message += "Your vitals are being monitored. Your care team will contact you if needed.\n\n"
    
    # Check if doctor reviewed
    if assessment.get('reviewed_by_doctor'):
        consultation_id = assessment.get('doctor_consultation_id')
        if consultation_id:
            consultation = consultations_repo.get_by_id(consultation_id)
            if consultation:
                message += f"""
<b>👨‍⚕️ Doctor's Assessment:</b>
{consultation.get('diagnosis', 'Under review')}

<b>Treatment Plan:</b>
{consultation.get('treatment_plan', 'Will be shared soon')}

<b>Next Visit:</b> {consultation.get('next_visit_date', 'To be scheduled')}
"""
    
    message += "\n\nUse /start to return to the main menu."
    
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother_id, {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed health summary'
    })
    
    return {'status': 'health_summary_sent'}


def handle_upload_docs_menu(chat_id):
    """
    Handle 📄 Upload Documents button.
    
    Shows instructions for uploading documents.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first.")
        return {'status': 'not_registered'}
    
    message = """
📄 <b>Upload Medical Documents</b>

You can upload:
• Lab reports
• Ultrasound scans
• Prescription documents
• Medical certificates

<b>How to upload:</b>
Simply send the photo or document file in this chat. Our AI will analyze it and add it to your medical records.

Use /start to return to the main menu.
"""
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother['_id'], {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed upload documents menu'
    })
    
    return {'status': 'upload_menu_sent'}


def handle_alerts_menu(chat_id):
    """
    Handle 🚨 Alerts button.
    
    Shows HIGH/CRITICAL alerts (read-only, no duplicates).
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first.")
        return {'status': 'not_registered'}
    
    mother_id = mother['_id']
    
    # Fetch HIGH/CRITICAL assessments
    all_assessments = assessments_repo.list_by_mother(mother_id, limit=10)
    high_risk_assessments = [
        a for a in all_assessments 
        if a.get('ai_evaluation', {}).get('risk_category') in ['HIGH', 'CRITICAL']
    ]
    
    if not high_risk_assessments:
        message = """
🟢 <b>Alerts</b>

No high-priority alerts at this time.

Your health is being monitored regularly. Keep attending your scheduled check-ups.

Use /start to return to the main menu.
"""
        telegram_service.send_message(chat_id, message)
        return {'status': 'no_alerts'}
    
    message = "🚨 <b>Important Alerts</b>\n\n"
    
    for assessment in high_risk_assessments[:3]:  # Show max 3 recent alerts
        risk_category = assessment.get('ai_evaluation', {}).get('risk_category', 'UNKNOWN')
        created_at = assessment.get('created_at', datetime.utcnow())
        date_str = created_at.strftime('%b %d, %Y') if isinstance(created_at, datetime) else 'Recent'
        
        risk_emoji = {'HIGH': '🟠', 'CRITICAL': '🔴'}.get(risk_category, '⚪')
        
        message += f"{risk_emoji} <b>{risk_category} Risk</b> - {date_str}\n"
        
        comm_output = assessment.get('ai_evaluation', {}).get('agent_outputs', {}).get('communication', {})
        if comm_output and comm_output.get('mother_message'):
            message += f"{comm_output['mother_message'][:150]}...\n\n"
        else:
            message += "Please contact your ASHA worker or doctor.\n\n"
    
    message += "Use /start to return to the main menu."
    
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother_id, {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed alerts'
    })
    
    return {'status': 'alerts_sent'}


def handle_doctor_messages(chat_id):
    """
    Handle 👩‍⚕️ Doctor Messages button.
    
    Shows last doctor message with timestamp and next visit.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first.")
        return {'status': 'not_registered'}
    
    mother_id = mother['_id']
    
    # Fetch messages from doctor
    doctor_messages = messages_repo.get_by_mother(mother_id, sender_type='doctor', limit=1)
    
    if not doctor_messages or len(doctor_messages) == 0:
        message = """
👨‍⚕️ <b>Doctor Messages</b>

No messages from your doctor yet.

Your doctor will review your assessments and provide guidance when needed.

Use /start to return to the main menu.
"""
        telegram_service.send_message(chat_id, message)
        return {'status': 'no_doctor_messages'}
    
    last_message = doctor_messages[0]
    
    doctor_name = last_message.get('sender_name', 'Doctor')
    message_text = last_message.get('message_text', 'No message content')
    created_at = last_message.get('created_at', datetime.utcnow())
    date_str = created_at.strftime('%b %d, %Y at %I:%M %p') if isinstance(created_at, datetime) else 'Recently'
    
    message = f"""
👨‍⚕️ <b>Latest Message from {doctor_name}</b>

<b>Sent:</b> {date_str}

<b>Message:</b>
{message_text}

Use /start to return to the main menu.
"""
    
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother_id, {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed doctor messages'
    })
    
    return {'status': 'doctor_messages_sent'}


def handle_document_upload(chat_id, document_or_photo):
    """
    Handle document/photo uploads from mothers.
    
    Saves file and creates documents record.
    Triggers document analysis (safe-fail).
    
    Args:
        chat_id: Telegram chat ID
        document_or_photo: Telegram document or photo object (photo is array, use largest)
    
    Returns:
        dict: Response status
    """
    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime
    from app.repositories import documents_repo
    
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first.")
        return {'status': 'not_registered'}
    
    mother_id = mother['_id']
    mother_name = mother.get('name', 'Unknown Mother')
    
    try:
        # Handle photo array (get largest size) or document object
        if isinstance(document_or_photo, list):
            # Photo - get largest size
            file_obj = max(document_or_photo, key=lambda x: x.get('file_size', 0))
            file_id = file_obj.get('file_id')
            filename = f"telegram_photo_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jpg"
            file_type = 'image/jpeg'
        else:
            # Document
            file_id = document_or_photo.get('file_id')
            filename = document_or_photo.get('file_name', f"telegram_doc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}")
            file_type = document_or_photo.get('mime_type', 'application/octet-stream')
        
        if not file_id:
            telegram_service.send_message(chat_id, "❌ Failed to process file. Please try again.")
            return {'status': 'no_file_id'}
        
        # Get file path from Telegram
        file_path = telegram_service.get_file_path(file_id)
        if not file_path:
            telegram_service.send_message(chat_id, "❌ Failed to download file. Please try again.")
            return {'status': 'download_failed'}
        
        # Ensure uploads directory exists
        upload_dir = os.path.join(current_app.root_path, '..', 'uploads', 'documents')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file locally
        safe_filename = secure_filename(filename)
        local_path = os.path.join(upload_dir, safe_filename)
        
        if not telegram_service.download_file(file_path, local_path):
            telegram_service.send_message(chat_id, "❌ Failed to save file. Please try again.")
            return {'status': 'save_failed'}
        
        # Get file size
        file_size = os.path.getsize(local_path)
        
        # Create document record in database
        document_data = {
            'mother_id': mother_id,
            'uploaded_by': 'mother',
            'uploaded_by_id': mother_id,
            'uploaded_by_name': mother_name,
            'document_type': 'general_document',  # Can be refined later
            'description': f'Uploaded by {mother_name} via Telegram',
            'telegram_file_id': file_id,
            'file_metadata': {
                'original_filename': filename,
                'stored_filename': safe_filename,
                'file_path': f'uploads/documents/{safe_filename}',
                'file_size_bytes': file_size,
                'file_type': file_type
            },
            'visible_to': ['mother', 'asha', 'doctor', 'admin'],
            'uploaded_at': datetime.utcnow()
        }
        
        document_id = documents_repo.create(document_data)
        
        current_app.logger.info(f"[TELEGRAM] Document {document_id} uploaded by mother {mother_id}")
        
        # Trigger AI analysis (safe-fail)
        try:
            from app.ai.document_analyzer import analyze_medical_document
            
            telegram_service.send_message(
                chat_id,
                "⏳ <b>Analyzing document...</b>\n\nPlease wait a moment."
            )
            
            analysis_result = analyze_medical_document(local_path, 'general_document', '')
            
            if analysis_result.get('success'):
                # Save AI analysis to document
                documents_repo.update(document_id, {
                    'ai_analysis': analysis_result.get('analysis'),
                    'extracted_text': analysis_result.get('extracted_text')
                })
                
                current_app.logger.info(f"[TELEGRAM] AI analysis completed for document {document_id}")
        except Exception as ai_error:
            current_app.logger.error(f"[TELEGRAM] AI analysis failed: {ai_error}")
            # Continue even if AI fails
        
        # Send notification to ASHA worker
        if mother.get('assigned_asha_id'):
            try:
                messages_repo.add_message(mother_id, {
                    'sender_type': 'system',
                    'sender_name': 'ArogyaMaa System',
                    'text': f'{mother_name} uploaded a new document via Telegram',
                    'from_mother': True,
                    'to_asha': True,
                    'to_asha_id': mother.get('assigned_asha_id'),
                    'document_id': document_id,
                    'read': False
                })
                current_app.logger.info(f"[TELEGRAM] ASHA notification sent for document {document_id}")
            except Exception as e:
                current_app.logger.error(f"[TELEGRAM] Failed to notify ASHA: {e}")
        
        # Success message to mother
        message = f"""
✅ <b>Document Uploaded Successfully!</b>

Your document has been:
• Saved to your medical records
• Sent to your ASHA worker: {mother.get('assigned_asha_name', 'Assigned ASHA')}
• Available for your doctor to review

{"🤖 AI analysis completed!" if analysis_result.get('success') else ""}

Your healthcare team will review it and contact you if needed.

Use /start to return to the main menu.
"""
        telegram_service.send_message(chat_id, message)
        
        # Log upload
        messages_repo.add_message(mother_id, {
            'sender_type': 'mother',
            'sender_name': mother_name,
            'text': f'Uploaded document: {filename}'
        })
        
        return {
            'status': 'document_uploaded',
            'document_id': str(document_id),
            'ai_analyzed': analysis_result.get('success', False)
        }
    
    except Exception as e:
        current_app.logger.error(f"[TELEGRAM] Document upload error: {e}", exc_info=True)
        telegram_service.send_message(
            chat_id,
            "❌ <b>Upload Failed</b>\n\nSorry, something went wrong. Please try again or contact your ASHA worker."
        )
        return {'status': 'error', 'error': str(e)}


def handle_send_message_menu(chat_id):
    """
    Handle 💬 Send Message button.
    
    Prompts mother to type a message that will be forwarded to doctor and ASHA.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first.")
        return {'status': 'not_registered'}
    
    # Get assigned healthcare team info
    team_info = []
    
    if mother.get('assigned_asha_id'):
        try:
            from app.repositories import asha_repo
            asha = asha_repo.get_by_id(mother['assigned_asha_id'])
            if asha:
                team_info.append(f"👩‍⚕️ ASHA Worker: {asha.get('name', 'N/A')}")
        except:
            pass
    
    if mother.get('assigned_doctor_id'):
        try:
            from app.repositories import doctors_repo
            doctor = doctors_repo.get_by_id(mother['assigned_doctor_id'])
            if doctor:
                team_info.append(f"👨‍⚕️ Doctor: {doctor.get('name', 'N/A')}")
        except:
            pass
    
    team_list = "\n".join(team_info) if team_info else "No healthcare team assigned yet"
    
    message = f"""
💬 <b>Send Message to Healthcare Team</b>

<b>Your Healthcare Team:</b>
{team_list}

<b>How to send a message:</b>
Just type your message and send it! It will be forwarded to your assigned doctor and ASHA worker.

<b>Examples:</b>
• "I'm feeling some pain in my abdomen"
• "When is my next checkup?"
• "Can I get a prescription for..."
• "I have a question about..."

Type your message now, or use /start to return to main menu.
"""
    
    telegram_service.send_message(chat_id, message)
    
    return {'status': 'send_message_prompt_shown'}


def _answer_callback_query(callback_query_id):
    """Answer callback query to remove loading state."""
    from app.services import telegram_service
    import requests
    
    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    payload = {'callback_query_id': callback_query_id}
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        current_app.logger.error(f"Failed to answer callback query: {e}")


def handle_help_command(chat_id):
    """
    Handle /help command - Show main menu.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first to register.")
        return {'status': 'not_registered'}
    
    _send_main_menu(chat_id, mother['name'])
    return {'status': 'help_sent'}


def handle_text_message(chat_id, text):
    """
    Handle regular text messages (not commands).

    Features:
    - AI registration flow (if active)
    - AI-powered nutrition recommendations (if asking about food/diet)
    - Message logging for healthcare team
    - Simple acknowledgment for other queries

    Args:
        chat_id: Telegram chat ID
        text: Message text

    Returns:
        dict: Response status
    """
    # Check if user is in active AI registration flow
    try:
        session = registration_repo.get_session(str(chat_id))
        if session and session.get('registration_active'):
            return handle_registration_message(chat_id, text)
    except Exception as e:
        current_app.logger.error(f"Registration session check error: {e}")

    mother = mothers_repo.get_by_telegram_chat_id(chat_id)

    if not mother:
        telegram_service.send_message(chat_id, "Please use /start first to register.")
        return {'status': 'not_registered'}
    
    mother_id = mother['_id']
    
    # Log the message
    messages_repo.add_message(mother_id, {
        'sender_type': 'mother',
        'sender_name': mother['name'],
        'text': text
    })
    
    # Check if this is a nutrition/food query
    if is_nutrition_query(text):
        try:
            # Send "thinking" message
            telegram_service.send_message(chat_id, "🤔 Let me check your health data and prepare personalized recommendations...")
            
            # Generate AI-powered nutrition recommendation
            nutrition_response = generate_nutrition_recommendation(mother_id, text)
            
            # Send the recommendation
            telegram_service.send_message(chat_id, nutrition_response)
            
            # Log AI interaction
            messages_repo.add_message(mother_id, {
                'sender_type': 'system',
                'sender_name': 'AI Nutrition Advisor',
                'text': f'Provided nutrition recommendation for query: "{text}"'
            })
            
            return {'status': 'nutrition_advice_sent', 'query': text}
            
        except Exception as e:
            current_app.logger.error(f"Nutrition AI error: {e}")
            # Fallback to standard response if AI fails
            message = """
⚠️ Unable to generate personalized recommendations right now.

Your message has been forwarded to your healthcare team. They will provide guidance soon.

Use /start to access the main menu.
"""
            telegram_service.send_message(chat_id, message)
            return {'status': 'nutrition_ai_failed', 'error': str(e)}
    
    else:
        # Non-nutrition query - standard acknowledgment
        message = """
Thank you for your message! 

Your healthcare team has been notified and will respond soon.

💡 <i>Tip: Ask me about nutrition or what to eat, and I can provide personalized dietary recommendations!</i>

Use /start to access the main menu.
"""
        telegram_service.send_message(chat_id, message)
        
        return {'status': 'message_logged'}


def handle_unknown_command(chat_id, command):
    """
    Handle unknown commands.
    
    Args:
        chat_id: Telegram chat ID
        command: Unknown command text
    
    Returns:
        dict: Response status
    """
    message = f"""
❓ Unknown command: {command}

Use /start to see the main menu.
"""
    telegram_service.send_message(chat_id, message)
    
    return {'status': 'unknown_command'}


# Legacy handlers (kept for backwards compatibility, redirects to menu)

def handle_status_command(chat_id):
    """Legacy /status handler - redirects to health summary."""
    return handle_health_summary(chat_id)


def handle_profile_command(chat_id):
    """Legacy /profile handler - redirects to main menu."""
    return handle_help_command(chat_id)



def handle_help_command(chat_id):
    """
    Handle /help command.
    
    Shows available commands and features.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        message = "Please use /start first to register."
        telegram_service.send_message(chat_id, message)
        return {'status': 'not_registered'}
    
    message = """
🌸 <b>ArogyaMaa - Available Commands</b>

<b>Basic Commands:</b>
/start - Start or restart the bot
/help - Show this help message
/status - View your current health status
/profile - View your profile information

<b>Health Monitoring:</b>
Your assigned ASHA worker will regularly check your health and enter vitals.
You'll receive alerts if anything needs attention.

<b>Communication:</b>
• Send messages to your ASHA worker or doctor anytime
• Upload medical documents (lab reports, scans)
• Receive health updates and appointment reminders

<b>Need Help?</b>
Just send a message describing what you need, and we'll assist you.

Your health and your baby's health are our priority! 💚
"""
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother['_id'], {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed help (/help command)'
    })
    
    return {'status': 'help_sent'}


def handle_status_command(chat_id):
    """
    Handle /status command.
    
    Shows mother's current health status and recent updates.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        message = "Please use /start first to register."
        telegram_service.send_message(chat_id, message)
        return {'status': 'not_registered'}
    
    # Build status message
    name = mother.get('name', 'Mother')
    age = mother.get('age', 'Not set')
    phone = mother.get('phone', 'Not set')
    
    # Check pregnancy info
    pregnancy = mother.get('current_pregnancy', {})
    edd = pregnancy.get('edd', 'Not set')
    gestational_weeks = pregnancy.get('gestational_age_weeks', 'Unknown')
    
    # Check ASHA and doctor assignment
    asha_assigned = "Assigned" if mother.get('assigned_asha_id') else "Not assigned yet"
    doctor_assigned = "Assigned" if mother.get('assigned_doctor_id') else "Not assigned yet"
    
    message = f"""
📊 <b>Your Health Status</b>

<b>Profile Information:</b>
👤 Name: {name}
🎂 Age: {age}
📱 Phone: {phone}

<b>Pregnancy Information:</b>
🤰 Gestational Age: {gestational_weeks} weeks
📅 Expected Delivery Date: {edd}

<b>Care Team:</b>
👩‍⚕️ ASHA Worker: {asha_assigned}
🩺 Doctor: {doctor_assigned}

<b>Recent Activity:</b>
No recent assessments yet. Your ASHA worker will conduct regular health checks.

Use /help to see what else you can do.
"""
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother['_id'], {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed status (/status command)'
    })
    
    return {'status': 'status_sent'}


def handle_profile_command(chat_id):
    """
    Handle /profile command.
    
    Shows detailed profile information.
    
    Args:
        chat_id: Telegram chat ID
    
    Returns:
        dict: Response status
    """
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    
    if not mother:
        message = "Please use /start first to register."
        telegram_service.send_message(chat_id, message)
        return {'status': 'not_registered'}
    
    name = mother.get('name', 'Not set')
    age = mother.get('age', 'Not set')
    phone = mother.get('phone', 'Not set')
    
    address = mother.get('address', {})
    village = address.get('village', 'Not set')
    district = address.get('district', 'Not set')
    state = address.get('state', 'Not set')
    
    medical_history = mother.get('medical_history', {})
    blood_group = medical_history.get('blood_group', 'Not set')
    
    message = f"""
👤 <b>Your Profile</b>

<b>Personal Information:</b>
Name: {name}
Age: {age}
Phone: {phone}
Blood Group: {blood_group}

<b>Address:</b>
Village: {village}
District: {district}
State: {state}

<b>Telegram ID:</b> {chat_id}

To update your profile, please contact your ASHA worker or send us a message.
"""
    telegram_service.send_message(chat_id, message)
    
    # Log interaction
    messages_repo.add_message(mother['_id'], {
        'sender_type': 'system',
        'sender_name': 'ArogyaMaa System',
        'text': 'Mother viewed profile (/profile command)'
    })
    
    return {'status': 'profile_sent'}


def handle_unknown_command(chat_id, command):
    """
    Handle unknown commands.
    
    Args:
        chat_id: Telegram chat ID
        command: Unknown command text
    
    Returns:
        dict: Response status
    """
    message = f"""
❓ Unknown command: {command}

Use /help to see all available commands.
"""
    telegram_service.send_message(chat_id, message)
    
    return {'status': 'unknown_command'}


# ==================== AI REGISTRATION HANDLERS (Webhook Mode) ====================


def handle_registration_start(chat_id):
    """
    Handle 📝 Register button press.

    Starts the AI-driven 25-question registration flow.
    If already fully registered, informs the user.
    """
    # Check if already completed full registration
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    if mother and mother.get('registration_complete'):
        telegram_service.send_message(
            chat_id,
            "✅ You are already registered! Use /start to access all features."
        )
        return {'status': 'already_registered'}

    reg_engine = _get_registration_engine()
    if not reg_engine:
        telegram_service.send_message(
            chat_id,
            "⚠️ Registration service is temporarily unavailable. Please try again later."
        )
        return {'status': 'registration_unavailable'}

    # Get or create registration session
    session = registration_repo.get_session(str(chat_id))
    if not session:
        # Pre-populate with the name from the mother profile
        full_name = mother['name'] if mother else 'Mother'
        session = {
            'telegram_chat_id': str(chat_id),
            'full_name': full_name,
            'registration_active': True,
        }
        registration_repo.update_session_data(str(chat_id), session)

    # Mark session as active
    if not session.get('registration_active'):
        registration_repo.update_session_data(str(chat_id), {'registration_active': True})
        session['registration_active'] = True

    # Get the first (or next) question
    _, next_q_text, is_comp, ui_details = reg_engine.provide_next_question(session)

    if is_comp:
        # Already answered all questions (edge case: resumed completed session)
        registration_repo.finalize_registration(str(chat_id))
        telegram_service.send_message(chat_id, next_q_text)
        return {'status': 'registration_already_complete'}

    # Send the question with appropriate keyboard
    keyboard = _get_keyboard_json(ui_details)
    telegram_service.send_message_with_keyboard(chat_id, next_q_text, keyboard)

    # Send voice response
    _run_tts_and_send(chat_id, next_q_text, session)

    return {'status': 'registration_started'}


def handle_registration_message(chat_id, text):
    """
    Process a text message during active AI registration.

    Args:
        chat_id: Telegram chat ID
        text: User's text response

    Returns:
        dict: Response status
    """
    reg_engine = _get_registration_engine()
    if not reg_engine:
        telegram_service.send_message(chat_id, "⚠️ Registration service unavailable.")
        return {'status': 'registration_unavailable'}

    session = registration_repo.get_session(str(chat_id))
    if not session:
        telegram_service.send_message(chat_id, "Please press the 📝 Register button to start.")
        return {'status': 'no_session'}

    # Run the registration engine
    extracted, next_q_text, is_comp, ui_details = reg_engine.provide_next_question(session, text)

    # Update session with extracted data
    if extracted:
        registration_repo.update_session_data(str(chat_id), extracted)

    # Refresh session for voice language
    new_session = registration_repo.get_session(str(chat_id))

    if is_comp:
        # Registration complete - finalize
        registration_repo.finalize_registration(str(chat_id))

        user_lang = new_session.get('preferred_language', 'Hindi')
        if 'English' in str(user_lang):
            final_msg = "✅ Registration Complete! Your health profile is now active. We will monitor your symptoms and notify your ASHA worker if needed."
        else:
            final_msg = "✅ पंजीकरण पूरा हुआ! आपका स्वास्थ्य प्रोफाइल अब सक्रिय है। हम आपके लक्षणों पर नजर रखेंगे और जरूरत पड़ने पर आपकी आशा वर्कर को सूचित करेंगे।"

        # Send with remove_keyboard to clear any reply keyboard
        telegram_service.send_message_with_keyboard(
            chat_id, final_msg, {"remove_keyboard": True}
        )
        _run_tts_and_send(chat_id, final_msg, new_session)

        current_app.logger.info(f"AI Registration completed for chat_id: {chat_id}")
        return {'status': 'registration_complete'}
    else:
        # Send next question
        keyboard = _get_keyboard_json(ui_details)
        telegram_service.send_message_with_keyboard(chat_id, next_q_text, keyboard)
        _run_tts_and_send(chat_id, next_q_text, new_session)

        return {'status': 'registration_in_progress'}


def handle_registration_voice(chat_id, voice_data):
    """
    Handle a voice message during active AI registration.

    Downloads the voice file, transcribes via Groq Whisper STT,
    then passes the transcribed text to handle_registration_message.

    Args:
        chat_id: Telegram chat ID
        voice_data: Telegram voice object from webhook

    Returns:
        dict: Response status
    """
    vp = _get_voice_processor()
    if not vp:
        telegram_service.send_message(chat_id, "⚠️ Voice processing unavailable.")
        return {'status': 'voice_unavailable'}

    try:
        file_id = voice_data.get('file_id')
        if not file_id:
            telegram_service.send_message(chat_id, "❌ Could not process voice message.")
            return {'status': 'no_file_id'}

        # Download the voice file
        file_path = telegram_service.get_file_path(file_id)
        if not file_path:
            telegram_service.send_message(chat_id, "❌ Could not download voice message.")
            return {'status': 'download_failed'}

        # Save locally
        tmp_dir = os.path.join(current_app.root_path, '..', 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        ogg_path = os.path.join(tmp_dir, f"voice_{file_id}.ogg")

        if not telegram_service.download_file(file_path, ogg_path):
            telegram_service.send_message(chat_id, "❌ Could not save voice message.")
            return {'status': 'save_failed'}

        # Transcribe using Groq Whisper
        transcribed_text = vp.audio_to_text(ogg_path)

        # Clean up the temporary file
        if os.path.exists(ogg_path):
            os.remove(ogg_path)

        if not transcribed_text or transcribed_text.startswith("Could not"):
            telegram_service.send_message(chat_id, "❌ Could not understand the voice message. Please try again or type your response.")
            return {'status': 'transcription_failed'}

        current_app.logger.info(f"Voice transcribed for {chat_id}: {transcribed_text[:50]}...")

        # Process as text
        return handle_registration_message(chat_id, transcribed_text)

    except Exception as e:
        current_app.logger.error(f"Voice registration error for {chat_id}: {e}")
        telegram_service.send_message(chat_id, "❌ Error processing voice. Please type your response instead.")
        return {'status': 'voice_error'}


def handle_registration_contact(chat_id, contact_data):
    """
    Handle a contact share during active AI registration.

    Extracts the phone number and passes it to the registration flow.

    Args:
        chat_id: Telegram chat ID
        contact_data: Telegram contact object from webhook

    Returns:
        dict: Response status
    """
    phone = contact_data.get('phone_number', '')
    if phone:
        return handle_registration_message(chat_id, phone)
    else:
        telegram_service.send_message(chat_id, "❌ Could not read phone number. Please type it manually.")
        return {'status': 'no_phone'}
