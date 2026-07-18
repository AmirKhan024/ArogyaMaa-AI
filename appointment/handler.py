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

import asyncio
import os
import uuid
import logging
from datetime import datetime, timezone

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


def _appt_lang(context) -> str:
    """The language ('hi'/'en') chosen for this appointment session."""
    return context.user_data.get('appointment_lang', 'hi')


def _resolve_lang(mother) -> str:
    """Map a mother's preferred_language ('English'/'हिंदी'/...) to 'en'/'hi'."""
    lang = str((mother or {}).get('preferred_language') or '').lower()
    return 'en' if 'english' in lang or lang == 'en' else 'hi'


# Bilingual strings used across the flow.
MSG = {
    'intro': {
        'hi': "📅 *अपॉइंटमेंट बुकिंग*\n\nमैं आपका अपॉइंटमेंट सहायक हूँ। मैं आपसे कुछ जानकारी लूँगा।\n\nआप बोलकर (voice message) या टाइप करके जवाब दे सकते हैं।",
        'en': "📅 *Appointment Booking*\n\nI'm your appointment assistant and will ask a few quick details.\n\nYou can answer by voice message or by typing.",
    },
    'cancel': {
        'hi': "❌ अपॉइंटमेंट रद्द किया गया। मेन मेनू पर लौटने के लिए /start टाइप करें।",
        'en': "❌ Appointment booking cancelled. Press /start to return to the main menu.",
    },
    'voice_error': {
        'hi': "माफ करें, आवाज़ सुनने में समस्या हुई। कृपया दोबारा बोलें या टाइप करें।",
        'en': "Sorry, I couldn't hear that clearly. Please try again by voice or typing.",
    },
    'save_error': {
        'hi': "माफ करें, अपॉइंटमेंट सेव करने में समस्या हुई। कृपया दोबारा कोशिश करें।",
        'en': "Sorry, something went wrong while saving your appointment. Please try again.",
    },
}


# ─── TTS helper (graceful degradation) ────────────────────────────────────────

async def _send_appt_voice_or_text(update, context, text: str):
    """Try TTS voice reply (in the session language); fall back to plain text."""
    try:
        from appointment.tts_sender import send_voice_reply
        hint = 'english' if _appt_lang(context) == 'en' else 'hindi'
        await send_voice_reply(update, context, text, language_hint=hint)
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

    # Try to pre-fill name/age/phone from the mother's profile (Postgres)
    pre_filled = False
    lang = 'hi'
    try:
        from app.repositories import mothers_repo
        mother = mothers_repo.get_by_telegram_chat_id(chat_id)
        lang = _resolve_lang(mother)

        if mother:
            # Link the booking to the mother record for dashboard views.
            context.user_data['appointment_data']['mother_id'] = str(mother['_id'])
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

                if lang == 'en':
                    pre_fill_msg = (
                        f"📅 *Appointment Booking*\n\n"
                        f"Your details:\n"
                        f"• Name: {name}\n"
                        f"• Age: {age}\n"
                        f"• Phone: {phone}\n\n"
                        f"Now, which date would you like?"
                    )
                else:
                    pre_fill_msg = (
                        f"📅 *अपॉइंटमेंट बुकिंग*\n\n"
                        f"आपकी जानकारी:\n"
                        f"• नाम: {name}\n"
                        f"• उम्र: {age}\n"
                        f"• फोन: {phone}\n\n"
                        f"अब कृपया अपॉइंटमेंट की तारीख बताएं।"
                    )
                await _send_appt_text(update, context, pre_fill_msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"[Appointment] Profile pre-fill failed: {e}")

    context.user_data['appointment_lang'] = lang
    context.user_data['appointment_data']['preferred_language'] = (
        'English' if lang == 'en' else 'हिंदी'
    )

    if not pre_filled:
        # No pre-fill — ask all 6 fields
        context.user_data['appointment_field_order'] = FULL_FIELD_ORDER
        await _send_appt_text(update, context, MSG['intro'][lang], parse_mode='Markdown')

    # Set first state
    field_order = context.user_data['appointment_field_order']
    first_state = field_order[0]
    context.user_data['appointment_state'] = first_state

    # Send the first prompt
    prompt = get_prompt_for_state(first_state, lang)
    await _send_appt_voice_or_text(update, context, prompt)


# ─── Cancel ───────────────────────────────────────────────────────────────────

async def cancel_appointment_flow(update, context):
    """Cancel the running appointment flow and clean up."""
    cancel_msg = MSG['cancel'][_appt_lang(context)]
    context.user_data.pop('appointment_active', None)
    context.user_data.pop('appointment_state', None)
    context.user_data.pop('appointment_data', None)
    context.user_data.pop('appointment_field_order', None)

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

            from appointment.tts_sender import TEMP_AUDIO_DIR as temp_dir
            os.makedirs(temp_dir, exist_ok=True)

            oga_path = os.path.join(temp_dir, f"appt_{uuid.uuid4()}.oga")
            await file.download_to_drive(oga_path)

            from appointment.transcriber import transcribe_audio
            # Sync Groq call — run off the event loop so the bot stays responsive.
            input_text = await asyncio.to_thread(transcribe_audio, oga_path)

            # Clean up
            if os.path.exists(oga_path):
                os.remove(oga_path)

        except Exception as e:
            logger.error(f"[Appointment] Voice transcription failed: {e}")
            await _send_appt_voice_or_text(update, context, MSG['voice_error'][_appt_lang(context)])
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
        prompt = get_prompt_for_state(next_state, _appt_lang(context))
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
    lang = _appt_lang(context)
    try:
        from appointment.excel_manager import is_slot_taken, write_appointment
        if is_slot_taken(preferred_date, preferred_time):
            if lang == 'en':
                conflict_msg = (
                    f"Sorry, the slot on {preferred_date} at {preferred_time} is already "
                    "booked. Please choose another date or time."
                )
            else:
                conflict_msg = (
                    f"माफ करें, {preferred_date} को {preferred_time} बजे का समय "
                    "पहले से बुक है। कृपया कोई दूसरा समय या तारीख चुनें।"
                )
            await _send_appt_voice_or_text(update, context, conflict_msg)

            # Reset date and time, re-ask
            data.pop("preferred_date", None)
            data.pop("preferred_time", None)
            context.user_data['appointment_state'] = APPT_STATES.ASK_DATE

            prompt = get_prompt_for_state(APPT_STATES.ASK_DATE, lang)
            await _send_appt_voice_or_text(update, context, prompt)
            return
    except Exception as e:
        logger.error(f"[Appointment] Conflict check failed: {e}")

    # ── Build appointment record ──────────────────────────────────────────────
    appointment_id = str(uuid.uuid4())
    security_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    appointment = {
        "appointment_id": appointment_id,
        "security_token": security_token,
        "patient_name": data.get("patient_name", ""),
        "patient_age": data.get("patient_age", ""),
        "patient_phone": data.get("patient_phone", ""),
        "telegram_chat_id": str(chat_id),
        "mother_id": data.get("mother_id"),
        "preferred_language": data.get("preferred_language", ""),
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

    # ── Persist appointment (Postgres) ────────────────────────────────────────
    try:
        from appointment.excel_manager import write_appointment
        write_appointment(appointment)
        logger.info(f"[Appointment] Saved: {appointment_id}")
    except Exception as e:
        logger.error(f"[Appointment] Save failed: {e}", exc_info=True)
        await _send_appt_voice_or_text(update, context, MSG['save_error'][lang])
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
    if lang == 'en':
        thanks_msg = (
            f"✅ Thank you, {appointment['patient_name']}!\n\n"
            f"📅 Your appointment is requested for {appointment['preferred_date']} "
            f"at {appointment['preferred_time']}.\n\n"
            "You'll get a Telegram message once the doctor confirms.\n\n"
            "Press /start to return to the main menu."
        )
    else:
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
