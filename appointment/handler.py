"""
Appointment Handler — Integration Glue

This module integrates the voice appointment booking flow into the
ArogyaMaa Telegram bot. It uses context.user_data state tracking
(NOT ConversationHandler) to avoid conflicts with the existing flat
handler architecture.

Key design decisions:
  - Uses context.user_data['appointment_active'] as a boolean gate
  - Uses context.user_data['appointment_state'] to track current step
  - Uses context.user_data['appointment_data'] to accumulate answers
  - Pre-fills name/age/phone from MongoDB if mother is registered
  - Falls back to text-only if TTS/STT fails
"""

import os
import uuid
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from appointment.state_machine import (
    APPT_STATES,
    FULL_FIELD_ORDER,
    SHORT_FIELD_ORDER,
    STATE_PARSERS,
    get_prompt_for_state,
    get_state_key,
    get_next_state,
)

logger = logging.getLogger(__name__)

# ─── TTS helper (graceful degradation) ────────────────────────────────────────

async def _send_appt_voice_or_text(update, context, text: str):
    """Try TTS voice reply; fall back to plain text if anything fails."""
    try:
        from appointment.tts_sender import send_voice_reply
        await send_voice_reply(update, context, text)
    except Exception as e:
        logger.warning(f"[Appointment] TTS unavailable, sending text: {e}")
        chat_id = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id, text=text)


async def _send_appt_text(update, context, text: str, reply_markup=None, parse_mode=None):
    """Send a plain text message to the user's chat."""
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id, text=text,
        reply_markup=reply_markup, parse_mode=parse_mode
    )


# ─── Entry Point (called from handle_callback_query) ─────────────────────────

async def start_appointment_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called when the user presses the '📅 Appointment' button.
    Sets up the appointment state in context.user_data.
    Pre-fills name/age/phone from MongoDB if available.
    """
    query = update.callback_query
    chat_id = update.effective_chat.id

    # Initialize appointment state
    context.user_data['appointment_active'] = True
    context.user_data['appointment_data'] = {}

    # Try to pre-fill from MongoDB
    pre_filled = False
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv()
        mongo_uri = os.getenv('MONGODB_URI', os.getenv('MONGO_URI', 'mongodb://localhost:27017'))
        db_name = os.getenv('MONGODB_DB_NAME', os.getenv('DB_NAME', 'ArogyaMaa'))
        client = MongoClient(mongo_uri)
        db = client[db_name]
        mother = db['mothers'].find_one({'telegram_chat_id': str(chat_id)})

        if mother:
            name = mother.get('name')
            age = mother.get('age')
            phone = mother.get('phone')

            if name and age and phone:
                # Pre-fill all 3 fields
                context.user_data['appointment_data']['patient_name'] = str(name)
                context.user_data['appointment_data']['patient_age'] = str(age)
                context.user_data['appointment_data']['patient_phone'] = str(phone)
                context.user_data['appointment_field_order'] = SHORT_FIELD_ORDER
                pre_filled = True

                # Show pre-fill info
                pre_fill_msg = (
                    f"📅 *अपॉइंटमेंट बुकिंग*\n\n"
                    f"आपकी जानकारी:\n"
                    f"• नाम: {name}\n"
                    f"• उम्र: {age}\n"
                    f"• फोन: {phone}\n\n"
                    f"अब कृपया अपॉइंटमेंट की तारीख बताएं।"
                )
                await _send_appt_text(update, context, pre_fill_msg, parse_mode='Markdown')

        client.close()
    except Exception as e:
        logger.error(f"[Appointment] MongoDB pre-fill failed: {e}")

    if not pre_filled:
        # No pre-fill — ask all 6 fields
        context.user_data['appointment_field_order'] = FULL_FIELD_ORDER

        intro_msg = (
            "📅 *अपॉइंटमेंट बुकिंग*\n\n"
            "मैं आपका अपॉइंटमेंट सहायक हूँ। "
            "मैं आपसे कुछ जानकारी लूँगा।\n\n"
            "आप बोलकर (voice message) या टाइप करके जवाब दे सकते हैं।"
        )
        await _send_appt_text(update, context, intro_msg, parse_mode='Markdown')

    # Set first state
    field_order = context.user_data['appointment_field_order']
    first_state = field_order[0]
    context.user_data['appointment_state'] = first_state

    # Send the first prompt
    prompt = get_prompt_for_state(first_state)
    await _send_appt_voice_or_text(update, context, prompt)


# ─── Cancel ───────────────────────────────────────────────────────────────────

async def cancel_appointment_flow(update, context):
    """Cancel the running appointment flow and clean up."""
    context.user_data.pop('appointment_active', None)
    context.user_data.pop('appointment_state', None)
    context.user_data.pop('appointment_data', None)
    context.user_data.pop('appointment_field_order', None)

    cancel_msg = "❌ अपॉइंटमेंट रद्द किया गया। मेन मेनू पर लौटने के लिए /start टाइप करें।"
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=cancel_msg)


# ─── Input Handler (called from handle_message) ──────────────────────────────

async def handle_appointment_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Processes a text or voice message during the appointment flow.
    Returns True if the message was handled (consumed), False otherwise.
    """
    if not context.user_data.get('appointment_active'):
        return False

    current_state = context.user_data.get('appointment_state')
    if current_state is None:
        return False

    # Check for cancel
    message_text = update.message.text if update.message and update.message.text else None
    if message_text and message_text.strip().lower() in ['/cancel', 'cancel', 'रद्द करें']:
        await cancel_appointment_flow(update, context)
        return True

    # ── Get input (voice or text) ─────────────────────────────────────────────
    input_text = None

    if update.message and update.message.voice:
        # Voice message — transcribe with Whisper
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)

            temp_dir = os.getenv("TEMP_AUDIO_DIR", "temp_audio/")
            os.makedirs(temp_dir, exist_ok=True)

            oga_path = os.path.join(temp_dir, f"appt_{uuid.uuid4()}.oga")
            await file.download_to_drive(oga_path)

            from appointment.transcriber import transcribe_audio
            input_text = transcribe_audio(oga_path)

            # Clean up
            if os.path.exists(oga_path):
                os.remove(oga_path)

        except Exception as e:
            logger.error(f"[Appointment] Voice transcription failed: {e}")
            error_msg = "माफ करें, आवाज़ सुनने में समस्या हुई। कृपया दोबारा बोलें या टाइप करें।"
            await _send_appt_voice_or_text(update, context, error_msg)
            return True

    elif message_text:
        input_text = message_text.strip()
    else:
        # Not a text or voice message — ignore
        return False

    if not input_text:
        return True

    # ── Parse input ───────────────────────────────────────────────────────────
    state_key = get_state_key(current_state)
    parser = STATE_PARSERS.get(current_state)
    parsed_value = parser(input_text) if parser else input_text

    # Store
    context.user_data['appointment_data'][state_key] = parsed_value
    logger.info(f"[Appointment] {state_key} = '{parsed_value}' (raw: '{input_text}')")

    # ── Advance to next state ─────────────────────────────────────────────────
    field_order = context.user_data.get('appointment_field_order', FULL_FIELD_ORDER)
    next_state = get_next_state(current_state, field_order)

    if next_state is None:
        # All fields collected — finalize
        await _finalize_appointment(update, context)
        return True
    else:
        context.user_data['appointment_state'] = next_state
        prompt = get_prompt_for_state(next_state)
        await _send_appt_voice_or_text(update, context, prompt)
        return True


# ─── Finalization ─────────────────────────────────────────────────────────────

async def _finalize_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    All fields collected. Check conflicts, write to Excel, email doctor.
    """
    chat_id = update.effective_chat.id
    data = context.user_data.get('appointment_data', {})

    preferred_date = data.get("preferred_date", "")
    preferred_time = data.get("preferred_time", "")

    # ── Conflict check ────────────────────────────────────────────────────────
    try:
        from appointment.excel_manager import is_slot_taken, write_appointment
        if is_slot_taken(preferred_date, preferred_time):
            conflict_msg = (
                f"माफ करें, {preferred_date} को {preferred_time} बजे का समय "
                "पहले से बुक है। कृपया कोई दूसरा समय या तारीख चुनें।"
            )
            await _send_appt_voice_or_text(update, context, conflict_msg)

            # Reset date and time, re-ask
            data.pop("preferred_date", None)
            data.pop("preferred_time", None)
            context.user_data['appointment_state'] = APPT_STATES.ASK_DATE

            prompt = get_prompt_for_state(APPT_STATES.ASK_DATE)
            await _send_appt_voice_or_text(update, context, prompt)
            return
    except Exception as e:
        logger.error(f"[Appointment] Conflict check failed: {e}")

    # ── Build appointment record ──────────────────────────────────────────────
    appointment_id = str(uuid.uuid4())
    security_token = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")

    appointment = {
        "appointment_id": appointment_id,
        "security_token": security_token,
        "patient_name": data.get("patient_name", ""),
        "patient_age": data.get("patient_age", ""),
        "patient_phone": data.get("patient_phone", ""),
        "telegram_chat_id": str(chat_id),
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
        "symptoms": data.get("symptoms", ""),
        "status": "Pending",
        "confirmed_date": "",
        "confirmed_time": "",
        "doctor_notes": "",
        "created_at": now,
        "updated_at": now,
    }

    # ── Write to Excel ────────────────────────────────────────────────────────
    try:
        from appointment.excel_manager import write_appointment
        write_appointment(appointment)
        logger.info(f"[Appointment] Written to Excel: {appointment_id}")
    except Exception as e:
        logger.error(f"[Appointment] Excel write failed: {e}", exc_info=True)
        error_msg = "माफ करें, अपॉइंटमेंट सेव करने में समस्या हुई। कृपया दोबारा कोशिश करें।"
        await _send_appt_voice_or_text(update, context, error_msg)
        _cleanup_appointment_state(context)
        return

    # ── Send doctor email (non-blocking) ──────────────────────────────────────
    try:
        from appointment.email_sender import send_doctor_email
        send_doctor_email(appointment)
        logger.info(f"[Appointment] Doctor email sent for: {appointment_id}")
    except Exception as e:
        logger.error(f"[Appointment] Email failed: {e}")
        # Appointment is saved — continue

    # ── Thank the patient ─────────────────────────────────────────────────────
    thanks_msg = (
        f"✅ धन्यवाद {appointment['patient_name']} जी!\n\n"
        f"📅 आपका अपॉइंटमेंट {appointment['preferred_date']} को "
        f"{appointment['preferred_time']} बजे के लिए अनुरोध किया गया है।\n\n"
        "डॉक्टर की पुष्टि होने पर आपको Telegram पर सूचित किया जाएगा।\n\n"
        "मुख्य मेनू पर लौटने के लिए /start दबाएं।"
    )

    try:
        await _send_appt_voice_or_text(update, context, thanks_msg)
    except Exception as e:
        logger.error(f"[Appointment] Thank you message failed: {e}")
        await context.bot.send_message(chat_id=chat_id, text=thanks_msg)

    # ── Cleanup state ─────────────────────────────────────────────────────────
    _cleanup_appointment_state(context)


def _cleanup_appointment_state(context):
    """Remove all appointment-related keys from user_data."""
    context.user_data.pop('appointment_active', None)
    context.user_data.pop('appointment_state', None)
    context.user_data.pop('appointment_data', None)
    context.user_data.pop('appointment_field_order', None)
