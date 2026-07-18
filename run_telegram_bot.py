"""
Telegram Bot - Complete Maternal Care System (Polling Mode)

Features:
- Mother self-registration via AI-driven 25-question flow with voice support
- Main menu with buttons (all users)
- AI nutrition advisor with time-aware recommendations
- Health summary, alerts, messages, document upload
- Direct communication with healthcare team
"""

import os
import sys
if sys.platform == 'win32':
    # cp1252 console can't print emoji/Devanagari; reconfigure in place so the
    # streams keep working under pytest capture and other wrappers.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
import asyncio
import logging
import shutil
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from groq import Groq

from app.db import init_db, get_engine
from app.repositories import (
    mothers_repo, messages_repo, assessments_repo, registration_repo,
)

# Load environment
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
FAST_MODEL = os.getenv('LLM_MODEL_FAST', 'llama-3.1-8b-instant')
# Optional: set HTTPS_PROXY in .env if Telegram is blocked in your region
# Example: HTTPS_PROXY=http://127.0.0.1:1080 or HTTPS_PROXY=socks5://127.0.0.1:1080
HTTPS_PROXY = os.getenv('HTTPS_PROXY', os.getenv('https_proxy', ''))

# Database Connection (Supabase / Postgres via SQLAlchemy).
# `db` is a truthy sentinel (the Engine) used throughout for "is the DB available?" checks.
db = None
try:
    init_db()
    db = get_engine()
    logger.info("✅ Postgres connected successfully")
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    db = None

# Groq AI Client
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("✅ Groq AI client initialized")
    except Exception as e:
        logger.error(f"❌ Groq client initialization failed: {e}")

# AI Registration Engine & Voice Processor
reg_engine = None
voice_processor = None

try:
    if GROQ_API_KEY:
        from app.ai.registration.assistant import AIAssistant
        from app.ai.registration.engine import RegistrationEngine
        from app.ai.registration.voice_processor import VoiceProcessor

        ai_assistant = AIAssistant(groq_api_key=GROQ_API_KEY)
        reg_engine = RegistrationEngine(ai_assistant)
        voice_processor = VoiceProcessor(groq_api_key=GROQ_API_KEY)
        logger.info("✅ AI Registration Engine initialized")
except Exception as e:
    logger.error(f"❌ AI Registration Engine init failed: {e}")

# Ensure tmp directory exists for voice processing (anchored to the repo root,
# not the process CWD, so the bot works no matter where it is launched from).
TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')
os.makedirs(TMP_DIR, exist_ok=True)


def _lang_code(preferred_language) -> str | None:
    """Map a stored preferred_language value to a Whisper ISO-639-1 hint."""
    lang = str(preferred_language or '').lower()
    if 'english' in lang or lang in ('en', 'eng'):
        return 'en'
    if 'marathi' in lang or 'मराठी' in lang:
        return 'mr'
    if 'hindi' in lang or 'हिंदी' in lang or 'हिन्दी' in lang:
        return 'hi'
    return None  # let Whisper auto-detect


def _fmt_ts(value, fmt='%b %d, %H:%M', default='recently'):
    """Format a timestamp that may be a datetime, an ISO string (JSONB), or None."""
    if hasattr(value, 'strftime'):
        return value.strftime(fmt)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime(fmt)
        except ValueError:
            return value[:16]
    return default


# ==================== VOICE HELPER ====================

async def send_voice_response(update_or_message, context, text, session):
    """Generate TTS voice and send to user."""
    if not voice_processor:
        return
    try:
        user_lang = session.get('preferred_language', 'Hindi')
        voice_path = await voice_processor.text_to_audio(text, lang=user_lang)
        if voice_path and os.path.exists(voice_path):
            # Determine chat_id from update or message
            if hasattr(update_or_message, 'chat_id'):
                chat_id = update_or_message.chat_id
            elif hasattr(update_or_message, 'effective_chat'):
                chat_id = update_or_message.effective_chat.id
            else:
                chat_id = update_or_message.chat.id
            with open(voice_path, 'rb') as vf:
                await context.bot.send_voice(chat_id=chat_id, voice=vf)
            os.remove(voice_path)
    except Exception as e:
        logger.error(f"TTS voice response error: {e}")


def get_registration_keyboard(ui_details):
    """Generate a Telegram keyboard from registration UI details."""
    ui_type = ui_details.get('type', 'text')
    options = ui_details.get('options', [])

    if ui_type in ['binary', 'choice'] and options:
        keyboard = [[KeyboardButton(opt)] for opt in options]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    elif ui_type == 'contact':
        keyboard = [[KeyboardButton("📱 Share Phone Number / अपना फोन नंबर साझा करें", request_contact=True)]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return ReplyKeyboardRemove()


# ==================== MAIN MENU ====================

def get_main_menu_keyboard():
    """Return the main menu inline keyboard."""
    keyboard = [
        [InlineKeyboardButton("🩺 Health Summary", callback_data='health_summary')],
        [InlineKeyboardButton("📄 Upload Documents", callback_data='upload_docs')],
        [InlineKeyboardButton("🚨 Alerts", callback_data='alerts')],
        [InlineKeyboardButton("👩‍⚕️ Doctor Messages", callback_data='messages')],
        [InlineKeyboardButton("💬 Send Message", callback_data='send_message')],
        [InlineKeyboardButton("📅 Appointment", callback_data='book_appointment')],
        [InlineKeyboardButton("📝 Register", callback_data='menu_register')]
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== /start COMMAND ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - always show the main menu."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    if db is None:
        await update.message.reply_text("❌ Database connection error. Please try again later.")
        return

    # Check if mother already registered
    existing_mother = mothers_repo.get_by_telegram_chat_id(chat_id)

    if existing_mother:
        mother_name = existing_mother.get('name', 'there')
        assigned_asha = existing_mother.get('assigned_asha_id')
        assigned_doctor = existing_mother.get('assigned_doctor_id')

        if assigned_asha and assigned_doctor:
            welcome_text = (
                f"👋 Welcome back, *{mother_name}*!\n\n"
                "✅ Your healthcare team is assigned.\n\n"
                "What would you like to do today?\n\n"
                "💬 *Tip:* You can also just type a message to send it to your doctor and ASHA worker!"
            )
        else:
            welcome_text = (
                f"👋 Welcome back, *{mother_name}*!\n\n"
                "⏳ Waiting for healthcare team assignment by admin.\n\n"
                "What would you like to do today?"
            )

        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    else:
        # New mother - create minimal profile then show menu
        first_name = user.first_name if user.first_name else 'Mother'
        last_name = user.last_name if user.last_name else ''
        full_name = f"{first_name} {last_name}".strip()
        username = user.username or ''

        mother_data = {
            'name': full_name,
            'age': None,
            'phone': None,
            'telegram_chat_id': str(chat_id),
            'telegram_username': username,
            'registered_via': 'telegram',
            'active': True,
            'risk_level': 'pending',
            'assigned_asha_id': None,
            'assigned_doctor_id': None,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }

        mothers_repo.create(mother_data)
        logger.info(f"✅ New mother profile created: {full_name} (chat_id: {chat_id})")

        welcome_message = (
            f"🌸 *Welcome to ArogyaMaa, {full_name}!* 🌸\n\n"
            "I'm here to help you during your pregnancy journey.\n\n"
            "Please press *📝 Register* to complete your health profile, "
            "or explore other options below:"
        )

        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


# ==================== STATUS & HELP COMMANDS ====================

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check registration and assignment status."""
    chat_id = update.effective_chat.id

    if db is None:
        await update.message.reply_text("❌ Database connection error.")
        return

    mother = mothers_repo.get_by_telegram_chat_id(chat_id)

    if not mother:
        await update.message.reply_text("❌ You are not registered yet.\nUse /start to begin.")
        return

    asha_assigned = mother.get('assigned_asha_id') is not None
    doctor_assigned = mother.get('assigned_doctor_id') is not None

    status_message = f"👤 *Your Status*\n\n"
    status_message += f"Name: {mother.get('name')}\n"
    status_message += f"Age: {mother.get('age', 'Not set')}\n"
    status_message += f"Gestational Week: {mother.get('gestational_age', 'Not set')}\n"
    status_message += f"Risk Level: {mother.get('risk_level', 'pending').upper()}\n\n"
    status_message += "*Healthcare Team Assignment:*\n"

    if asha_assigned and doctor_assigned:
        status_message += "✅ ASHA Worker: Assigned\n✅ Doctor: Assigned\n\nYour healthcare team is ready! 💚"
    elif asha_assigned:
        status_message += "✅ ASHA Worker: Assigned\n⏳ Doctor: Pending\n"
    elif doctor_assigned:
        status_message += "⏳ ASHA Worker: Pending\n✅ Doctor: Assigned\n"
    else:
        status_message += "⏳ ASHA Worker: Pending\n⏳ Doctor: Pending\n\nAdmin will assign your team soon."

    await update.message.reply_text(status_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message."""
    help_text = (
        "🌸 *ArogyaMaa Bot Commands* 🌸\n\n"
        "/start - Main menu with options\n"
        "/status - Check your assignment status\n"
        "/help - Show this help message\n\n"
        "*Main Menu Options:*\n"
        "🩺 Health Summary - View latest assessment\n"
        "📄 Upload Documents - Send lab reports\n"
        "🚨 Alerts - View important notifications\n"
        "👩‍⚕️ Doctor Messages - See messages from your team\n"
        "💬 Send Message - Contact your healthcare team\n"
        "📅 Appointment - Book a doctor appointment (voice/text)\n"
        "📝 Register - Complete your health profile\n\n"
        "*Ask me anything!*\n"
        "Just type questions like:\n"
        "• What should I eat for dinner?\n"
        "• Can I exercise?\n\n"
        "I'll provide personalized advice based on your health data! 🤰💚"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


# ==================== MENU CALLBACK HANDLERS ====================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses from main menu."""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    callback_data = query.data

    if callback_data == 'health_summary':
        await show_health_summary(chat_id, query)
    elif callback_data == 'upload_docs':
        await show_upload_instructions(chat_id, query)
    elif callback_data == 'alerts':
        await show_alerts(chat_id, query)
    elif callback_data == 'messages':
        await show_messages(chat_id, query)
    elif callback_data == 'send_message':
        await show_send_message_prompt(chat_id, query)
    elif callback_data == 'book_appointment':
        await show_appointment_menu(chat_id, query)
    elif callback_data == 'appt_book_new':
        from appointment.handler import start_appointment_flow
        await start_appointment_flow(update, context)
    elif callback_data == 'appt_my_list':
        await show_my_appointments(chat_id, query)
    elif callback_data.startswith('appt_cancel:'):
        await cancel_my_appointment(chat_id, query, callback_data.split(':', 1)[1])
    elif callback_data == 'menu_register':
        await handle_register_button(update, context)


async def show_health_summary(chat_id, query):
    """Show latest health assessment and AI summary."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return

    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    if not mother:
        await query.edit_message_text("Please use /start first.")
        return

    assessments = assessments_repo.list_by_mother(mother['_id'], limit=1)

    if not assessments:
        message = (
            "📋 *Health Summary*\n\n"
            "No health assessments yet.\n\n"
            "Your ASHA worker will conduct regular health checks.\n\n"
            "Use /start to return to the main menu."
        )
        await query.edit_message_text(message, parse_mode='Markdown')
        return

    assessment = assessments[0]
    vitals = assessment.get('vitals', {})
    ai_eval = assessment.get('ai_evaluation', {})

    bp_sys = vitals.get('bp_systolic', 'N/A')
    bp_dia = vitals.get('bp_diastolic', 'N/A')
    hb = vitals.get('hemoglobin') or vitals.get('hemoglobin_g_dl') or 'N/A'
    
    # Fallback to mother's profile for weight if missing in assessment
    weight = vitals.get('weight') or vitals.get('weight_kg')
    if not weight:
        weight = mother.get('medical_history', {}).get('weight', 'N/A')
        
    pulse = vitals.get('pulse') or vitals.get('heart_rate') or 'N/A'

    risk_level = ai_eval.get('risk_category', 'UNKNOWN').upper()
    risk_emoji = {'LOW': '🟢', 'MODERATE': '🟡', 'HIGH': '🟠', 'CRITICAL': '🔴'}.get(risk_level, '⚪')

    # Format timestamp nicely
    ts = assessment.get('timestamp')
    if hasattr(ts, 'strftime'):
        date_str = ts.strftime('%d %B %Y at %I:%M %p')
    else:
        date_str = str(ts)[:16] if ts else 'N/A'

    message = (
        f"📋 *Your Health Summary*\n\n"
        f"{risk_emoji} *Risk Level:* {risk_level}\n\n"
        f"*Latest Vitals:*\n"
        f"• Blood Pressure: {bp_sys}/{bp_dia} mmHg\n"
        f"• Hemoglobin: {hb} g/dL\n"
        f"• Weight: {weight} kg\n"
        f"• Pulse/Heart Rate: {pulse} bpm\n\n"
        f"*Assessment Date:* {date_str}\n\n"
        f"Use /start to return to the main menu."
    )
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_upload_instructions(chat_id, query):
    """Show instructions for uploading documents."""
    message = (
        "📄 *Upload Medical Documents*\n\n"
        "You can upload:\n"
        "• Lab reports (PDF, JPG)\n"
        "• Ultrasound scans (JPG, PNG)\n"
        "• Prescription images\n\n"
        "*How to upload:*\n"
        "1. Click the attachment icon 📎\n"
        "2. Select your document/photo\n"
        "3. Send it to me\n\n"
        "I'll save it to your medical records and notify your doctor.\n\n"
        "Use /start to return to the main menu."
    )
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_alerts(chat_id, query):
    """Show critical alerts and notifications."""
    message = (
        "🚨 *Alerts & Notifications*\n\n"
        "No critical alerts at this time. ✅\n\n"
        "You will be notified here if:\n"
        "• Your vitals show concerning trends\n"
        "• Doctor schedules an appointment\n"
        "• ASHA needs to visit you\n"
        "• Important reminders\n\n"
        "Use /start to return to the main menu."
    )
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_messages(chat_id, query):
    """Show recent messages from doctor/ASHA."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return

    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    if not mother:
        await query.edit_message_text("Please use /start first.")
        return

    recent_messages = messages_repo.list_notifications_for_mother(
        mother['_id'], limit=5, exclude_from_mother=True
    )

    if not recent_messages:
        message = (
            "👩‍⚕️ *Doctor Messages*\n\n"
            "No messages from your healthcare team yet.\n\n"
            "They will send you updates, advice, and follow-up instructions here.\n\n"
            "Use /start to return to the main menu."
        )
    else:
        message = "👩‍⚕️ *Recent Messages*\n\n"
        for msg in recent_messages:
            sender = msg.get('sender_name', 'Healthcare Team')
            content = msg.get('content', '')
            # timestamp may be a datetime or an ISO string (JSONB round-trip)
            message += f"*{sender}* ({_fmt_ts(msg.get('timestamp'))})\n{content}\n\n"
        message += "Use /start to return to the main menu."

    await query.edit_message_text(message, parse_mode='Markdown')


async def show_send_message_prompt(chat_id, query):
    """Prompt mother to send a message."""
    message = (
        "💬 *Send a Message*\n\n"
        "Just type your message below and send it!\n\n"
        "Your message will be delivered to:\n"
        "• Your assigned doctor 👨‍⚕️\n"
        "• Your ASHA worker 👩‍⚕️\n\n"
        "They will respond as soon as possible.\n\n"
        "Type your message now... ✍️"
    )
    await query.edit_message_text(message, parse_mode='Markdown')


# ==================== APPOINTMENT MENU ====================

def _is_en(mother) -> bool:
    return 'english' in str((mother or {}).get('preferred_language') or '').lower()


async def show_appointment_menu(chat_id, query):
    """📅 button → submenu: view my appointments / book a new one."""
    mother = mothers_repo.get_by_telegram_chat_id(chat_id) if db is not None else None
    en = _is_en(mother)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 My appointments" if en else "📋 मेरी अपॉइंटमेंट", callback_data='appt_my_list')],
        [InlineKeyboardButton("➕ Book new appointment" if en else "➕ नई अपॉइंटमेंट बुक करें", callback_data='appt_book_new')],
    ])
    text = ("📅 *Appointments*\n\nWhat would you like to do?" if en
            else "📅 *अपॉइंटमेंट*\n\nआप क्या करना चाहेंगी?")
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)


_APPT_STATUS_LABELS = {
    'Pending':     {'en': '🟡 Waiting for doctor', 'hi': '🟡 डॉक्टर की पुष्टि बाकी'},
    'Confirmed':   {'en': '🟢 Confirmed',           'hi': '🟢 पुष्टि हो गई'},
    'Rescheduled': {'en': '🔵 Rescheduled',         'hi': '🔵 समय बदला गया'},
    'Cancelled':   {'en': '🔴 Cancelled',           'hi': '🔴 रद्द'},
}


async def show_my_appointments(chat_id, query):
    """List the mother's appointments with status; allow cancelling pending ones."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return
    from app.repositories import appointments_repo
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    en = _is_en(mother)
    appts = appointments_repo.list_by_chat_id(chat_id, limit=5)

    if not appts:
        text = ("📋 *My appointments*\n\nYou have no appointments yet.\n"
                "Book one with the button below!" if en else
                "📋 *मेरी अपॉइंटमेंट*\n\nअभी कोई अपॉइंटमेंट नहीं है।\n"
                "नीचे बटन से बुक करें!")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Book appointment" if en else "➕ अपॉइंटमेंट बुक करें",
                                 callback_data='appt_book_new')
        ]])
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
        return

    lang = 'en' if en else 'hi'
    lines = ["📋 *My appointments*" if en else "📋 *मेरी अपॉइंटमेंट*", ""]
    buttons = []
    for a in appts:
        status = a.get('status', 'Pending')
        label = _APPT_STATUS_LABELS.get(status, {}).get(lang, status)
        slot_date = a.get('confirmed_date') or a.get('preferred_date') or '?'
        slot_time = a.get('confirmed_time') or a.get('preferred_time') or '?'
        lines.append(f"• {slot_date} {slot_time} — {label}")
        if a.get('doctor_notes'):
            lines.append(f"  📝 {a['doctor_notes']}")
        if status == 'Pending':
            buttons.append([InlineKeyboardButton(
                (f"❌ Cancel {slot_date} {slot_time}" if en else f"❌ रद्द करें {slot_date} {slot_time}"),
                callback_data=f"appt_cancel:{a.get('appointment_id')}")])
    lines.append("")
    lines.append("Use /start for the main menu." if en else "मुख्य मेनू के लिए /start दबाएं।")
    buttons.append([InlineKeyboardButton("➕ Book new" if en else "➕ नई बुकिंग",
                                         callback_data='appt_book_new')])
    await query.edit_message_text("\n".join(lines), parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def cancel_my_appointment(chat_id, query, appointment_id):
    """Mother cancels her own pending appointment."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return
    from app.repositories import appointments_repo
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    en = _is_en(mother)

    appt = appointments_repo.get_by_appointment_id(appointment_id)
    if not appt or str(appt.get('telegram_chat_id')) != str(chat_id):
        await query.edit_message_text("❌ Appointment not found." if en else "❌ अपॉइंटमेंट नहीं मिली।")
        return

    appointments_repo.update_status(appointment_id, "Cancelled",
                                    doctor_notes="Cancelled by patient via Telegram")
    text = ("✅ Your appointment has been cancelled.\n\nYou can book a new one anytime "
            "from the 📅 menu. Use /start for the main menu." if en else
            "✅ आपकी अपॉइंटमेंट रद्द कर दी गई है।\n\nआप 📅 मेनू से कभी भी नई बुकिंग कर "
            "सकती हैं। मुख्य मेनू के लिए /start दबाएं।")
    await query.edit_message_text(text)


# ==================== AI REGISTRATION HANDLERS ====================

# One lock per chat serializes registration processing. Without it, answering by
# voice AND text (or a fast double-send) advances the flow twice — duplicated
# and skipped questions.
_reg_locks: dict = {}


def _get_reg_lock(chat_id) -> asyncio.Lock:
    return _reg_locks.setdefault(chat_id, asyncio.Lock())


async def handle_register_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 📝 Register button - start the guided registration."""
    query = update.callback_query
    chat_id = query.message.chat.id

    if not reg_engine:
        await query.message.reply_text("⚠️ Registration service is temporarily unavailable.")
        return

    # Check if already completed full registration
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    if mother and mother.get('registration_complete'):
        await query.message.reply_text("✅ You are already registered! Use /start to access all features.")
        return

    # Get or create registration session
    session = registration_repo.get_session(chat_id)
    if not session:
        full_name = mother['name'] if mother else (query.from_user.first_name or None)
        session = {
            "telegram_chat_id": str(chat_id),
            "registration_active": True,
        }
        if full_name:
            session["full_name"] = full_name
        registration_repo.update_session_data(chat_id, session)

    # Ensure registration is marked active
    if not session.get('registration_active'):
        registration_repo.update_session_data(chat_id, {"registration_active": True})
        session['registration_active'] = True

    # First (or next) question — engine runs off the event loop.
    _, next_q_text, is_comp, ui_details = await asyncio.to_thread(
        reg_engine.provide_next_question, session
    )

    if is_comp:
        # Edge case: session was already complete
        _finalize_polling_registration(str(chat_id))
        await query.message.reply_text(next_q_text, reply_markup=ReplyKeyboardRemove())
        return

    await query.message.reply_text(
        next_q_text,
        reply_markup=get_registration_keyboard(ui_details)
    )
    await send_voice_response(query.message, context,
                              ui_details.get('speech_text') or next_q_text, session)


async def handle_registration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process text/voice/contact input during active registration (serialized per chat)."""
    chat_id = update.effective_chat.id
    lock = _get_reg_lock(chat_id)

    # A second message while we're still processing the first would double-advance
    # the flow — acknowledge once and drop it.
    if lock.locked():
        if not context.user_data.get('reg_busy_notified'):
            context.user_data['reg_busy_notified'] = True
            await update.message.reply_text("🙏 एक क्षण... / One moment...")
        return True

    # Ignore re-delivered updates (Telegram retries).
    if context.user_data.get('last_reg_update_id', -1) >= update.update_id:
        return True
    context.user_data['last_reg_update_id'] = update.update_id

    async with lock:
        try:
            return await _process_registration_input(update, context, chat_id)
        finally:
            context.user_data['reg_busy_notified'] = False


async def _process_registration_input(update, context, chat_id):
    session = registration_repo.get_session(chat_id)

    if not session or not session.get('registration_active'):
        return False  # Not in registration - let caller handle

    if not reg_engine:
        await update.message.reply_text("⚠️ Registration service unavailable.")
        return True

    # Extract text from different input types
    if update.message.contact:
        text_content = update.message.contact.phone_number
    elif update.message.voice:
        if not voice_processor:
            await update.message.reply_text("⚠️ Voice processing unavailable. Please type your response.")
            return True
        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            ogg_path = os.path.join(TMP_DIR, f"{update.message.voice.file_id}.ogg")
            await voice_file.download_to_drive(ogg_path)
            # Sync Groq call — run off the event loop; honor the mother's language.
            text_content = await asyncio.to_thread(
                voice_processor.audio_to_text, ogg_path,
                _lang_code(session.get('preferred_language')),
            )
            if os.path.exists(ogg_path):
                os.remove(ogg_path)
            if not text_content or text_content.startswith("Could not"):
                await update.message.reply_text("❌ Could not understand the voice message. Please try again or type your response.")
                return True
            logger.info(f"Voice transcribed for {chat_id}: {text_content[:50]}...")
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            await update.message.reply_text("❌ Error processing voice. Please type your response.")
            return True
    else:
        text_content = update.message.text

    # Run the registration engine off the event loop (it may call the LLM).
    extracted, next_q_text, is_comp, ui_details = await asyncio.to_thread(
        reg_engine.provide_next_question, session, text_content
    )

    # Update session data
    if extracted:
        registration_repo.update_session_data(chat_id, extracted)

    # Refresh session for language detection
    new_session = registration_repo.get_session(chat_id)

    if is_comp:
        # Registration complete — the engine's message includes name/week/next steps.
        _finalize_polling_registration(str(chat_id))
        context.user_data['reg_completed_at'] = datetime.now(timezone.utc).timestamp()

        await update.message.reply_text(next_q_text, reply_markup=ReplyKeyboardRemove())
        await send_voice_response(update.message, context,
                                  ui_details.get('speech_text') or next_q_text, new_session)

        logger.info(f"✅ Registration completed for chat_id: {chat_id}")
    else:
        await update.message.reply_text(
            next_q_text,
            reply_markup=get_registration_keyboard(ui_details)
        )
        await send_voice_response(update.message, context,
                                  ui_details.get('speech_text') or next_q_text, new_session)

    return True


def _finalize_polling_registration(telegram_chat_id):
    """Move registration session data into the mothers table (delegates to the repo)."""
    return registration_repo.finalize_registration(telegram_chat_id)


# ==================== AI NUTRITION ADVISOR ====================

def get_time_context():
    """Determine meal context based on current time."""
    now = datetime.now()
    hour = now.hour

    if 5 <= hour < 10:
        return {"meal_type": "breakfast", "greeting": "Good morning", "time_specific": "Start your day with a nutritious breakfast"}
    elif 10 <= hour < 12:
        return {"meal_type": "mid_morning_snack", "greeting": "Good morning", "time_specific": "A healthy mid-morning snack will keep you energized"}
    elif 12 <= hour < 15:
        return {"meal_type": "lunch", "greeting": "Good afternoon", "time_specific": "Let's plan a balanced lunch for you"}
    elif 15 <= hour < 17:
        return {"meal_type": "afternoon_snack", "greeting": "Good afternoon", "time_specific": "A nutritious snack will help you stay active"}
    elif 17 <= hour < 21:
        return {"meal_type": "dinner", "greeting": "Good evening", "time_specific": "Let's prepare a healthy dinner"}
    else:
        return {"meal_type": "night_snack", "greeting": "Good evening", "time_specific": "If you're hungry, here's what you can have"}


def is_nutrition_query(message_text):
    """Check if message is about food/nutrition."""
    message_lower = message_text.lower()
    nutrition_keywords = [
        'eat', 'food', 'dinner', 'lunch', 'breakfast', 'snack',
        'hungry', 'meal', 'diet', 'nutrition', 'recipe', 'cook',
        'drink', 'vegetable', 'fruit', 'protein', 'vitamin',
        'should i have', 'can i eat', 'what to eat'
    ]
    return any(keyword in message_lower for keyword in nutrition_keywords)


async def generate_ai_nutrition_response(mother, message_text):
    """Generate AI nutrition recommendation based on health data and time."""
    if not groq_client:
        return None

    try:
        time_ctx = get_time_context()

        assessments = assessments_repo.list_by_mother(mother['_id'], limit=1)

        context = f"""
{time_ctx['greeting']}! {time_ctx['time_specific']}.

MOTHER'S PROFILE:
- Name: {mother.get('name')}
- Age: {mother.get('age', 'Unknown')}
- Gestational Week: {mother.get('gestational_age', 'Unknown')}
"""

        if assessments:
            assessment = assessments[0]
            vitals = assessment.get('vitals', {})
            ai_eval = assessment.get('ai_evaluation', {})
            context += f"""
LATEST HEALTH DATA:
- BP: {vitals.get('bp_systolic', 'N/A')}/{vitals.get('bp_diastolic', 'N/A')} mmHg
- Hemoglobin: {vitals.get('hemoglobin', 'N/A')} g/dL
- Weight: {vitals.get('weight', 'N/A')} kg
- Risk Level: {ai_eval.get('risk_category', 'UNKNOWN')}
"""

        prompt = f"""You are a maternal nutrition AI assistant for a pregnant woman in India.

CONTEXT:
{context}

MOTHER'S QUESTION:
"{message_text}"

INSTRUCTIONS:
1. Consider the current time of day ({time_ctx['meal_type']})
2. Consider her health data (BP, hemoglobin, risk level)
3. Provide specific Indian meal suggestions
4. Keep it conversational, warm, and caring
5. Include portion sizes and preparation tips
6. Mention nutrients and benefits
7. Keep response under 300 words

Provide a personalized nutrition recommendation:
"""

        response = groq_client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": "You are a caring maternal nutrition advisor in India."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"AI nutrition error: {e}")
        return None


# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages from mothers - checks appointment, registration, then nutrition/default."""
    chat_id = update.effective_chat.id

    # Check if user is in active APPOINTMENT flow (highest priority)
    if context.user_data.get('appointment_active'):
        from appointment.handler import handle_appointment_input
        handled = await handle_appointment_input(update, context)
        if handled:
            return

    # Check if user is in active AI registration flow
    if db is not None:
        session = registration_repo.get_session(chat_id)
        if session and session.get('registration_active'):
            handled = await handle_registration_input(update, context)
            if handled:
                return

    if db is None:
        return

    message_text = update.message.text if update.message.text else ''
    mother = mothers_repo.get_by_telegram_chat_id(chat_id)

    if not mother:
        await update.message.reply_text("Please register first using /start")
        return

    # Check if it's a nutrition query
    if message_text and is_nutrition_query(message_text):
        await update.message.chat.send_action(action="typing")

        ai_response = await generate_ai_nutrition_response(mother, message_text)

        if ai_response:
            response_text = f"🥗 *Nutrition Advice*\n\n{ai_response}\n\n💚 Stay healthy!"
            await update.message.reply_text(response_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                "I'm having trouble generating a response right now. "
                "Please consult your doctor or ASHA worker for nutrition advice."
            )
    else:
        # A voice note (no text) outside any flow — guide instead of a dead-end ack.
        if not message_text:
            lang = _lang_code(mother.get('preferred_language'))
            # Straggler inputs right after registration completes get a warm nudge,
            # not a confusing generic ack.
            completed_at = context.user_data.get('reg_completed_at', 0)
            if completed_at and datetime.now(timezone.utc).timestamp() - completed_at < 600:
                if lang == 'en':
                    await update.message.reply_text(
                        "💚 Your registration is already complete! Press /start for your "
                        "health menu, or type a message anytime for your care team."
                    )
                else:
                    await update.message.reply_text(
                        "💚 आपका पंजीकरण पूरा हो चुका है! /start दबाकर मेनू देखें, या अपनी "
                        "टीम के लिए कभी भी संदेश लिखें।"
                    )
                return
            if lang == 'en':
                await update.message.reply_text(
                    "💚 I can take voice answers during registration and appointment "
                    "booking. To message your care team, please type it out — or press "
                    "/start for the menu."
                )
            else:
                await update.message.reply_text(
                    "💚 पंजीकरण और अपॉइंटमेंट के दौरान आप बोलकर जवाब दे सकती हैं। "
                    "अपनी टीम को संदेश भेजने के लिए कृपया लिखें — या /start दबाएं।"
                )
            return

        # Regular message — route to the assigned care team so it shows up in the
        # ASHA and doctor dashboards (unrouted messages are backfilled on assignment).
        asha_id = mother.get('assigned_asha_id')
        doctor_id = mother.get('assigned_doctor_id')
        message_data = {
            'mother_id': str(mother['_id']),
            'mother_name': mother.get('name'),
            'telegram_chat_id': str(chat_id),
            'message_type': 'from_mother',
            'sender_name': mother.get('name') or 'Mother',
            'content': message_text,
            'message': message_text,
            'read': False,
        }
        if asha_id:
            message_data['to_asha_id'] = str(asha_id)
        if doctor_id:
            message_data['to_doctor_id'] = str(doctor_id)
        messages_repo.create(message_data)

        lang = _lang_code(mother.get('preferred_language'))
        if asha_id or doctor_id:
            reply = (
                "📨 Message sent to your care team ✅ They will respond soon.\n\n"
                "For emergencies, please call your local health center."
            ) if lang == 'en' else (
                "📨 आपका संदेश आपकी देखभाल टीम को भेज दिया गया ✅ वे जल्द जवाब देंगे।\n\n"
                "आपातकाल में कृपया अपने स्वास्थ्य केंद्र को फोन करें।"
            )
        else:
            reply = (
                "📨 Your message is saved. You'll be connected to an ASHA worker and "
                "doctor soon — they will see it as soon as they are assigned.\n\n"
                "For emergencies, please call your local health center."
            ) if lang == 'en' else (
                "📨 आपका संदेश सुरक्षित है। जल्द ही आपको आशा दीदी और डॉक्टर से जोड़ा "
                "जाएगा — नियुक्त होते ही वे इसे देख लेंगे।\n\n"
                "आपातकाल में कृपया अपने स्वास्थ्य केंद्र को फोन करें।"
            )
        await update.message.reply_text(reply)


# ==================== MAIN ====================

def main():
    """Start the bot in polling mode."""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in .env file")
        return

    if db is None:
        logger.error("Database connection failed (check DATABASE_URL)")
        return

    logger.info("Bot token found: %s...", BOT_TOKEN[:10])
    logger.info("Postgres connected")
    if reg_engine:
        logger.info("AI Registration Engine ready")
    if voice_processor:
        logger.info("Voice Processor ready (STT + TTS)")
    if shutil.which('ffmpeg'):
        logger.info("ffmpeg found - voice replies (TTS) enabled")
    else:
        logger.warning(
            "*** ffmpeg NOT FOUND on PATH - TTS voice replies will silently fall back "
            "to text! Install ffmpeg (https://ffmpeg.org) to enable voice notes. ***"
        )
    logger.info("Starting Telegram bot...")
    logger.info("Bot is running! Press Ctrl+C to stop.")

    # Pre-flight connectivity check
    import httpx as _httpx
    logger.info("Checking connectivity to Telegram API...")
    try:
        _test_client = _httpx.Client(timeout=10, proxy=HTTPS_PROXY if HTTPS_PROXY else None)
        _resp = _test_client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
        _test_client.close()
        if _resp.status_code == 200:
            bot_info = _resp.json().get('result', {})
            logger.info("Connected to Telegram! Bot: @%s", bot_info.get('username', 'unknown'))
        else:
            logger.warning("Telegram API returned status %s", _resp.status_code)
    except Exception as _e:
        logger.warning("Cannot reach api.telegram.org: %s", _e)
        logger.warning(
            "Possible causes: (1) no internet, (2) Telegram blocked by ISP/firewall, "
            "(3) VPN/proxy needed - set HTTPS_PROXY in .env "
            "(e.g. HTTPS_PROXY=http://127.0.0.1:1080). Will keep retrying..."
        )

    # Capture the bot's event loop once it is running, so the appointment webhook
    # thread can schedule patient notifications onto it safely.
    async def _post_init(application):
        from appointment.webhook_server import set_bot_loop
        set_bot_loop(asyncio.get_running_loop())

    # Create application with increased timeouts for flaky networks
    builder = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
    )

    # Add proxy support if configured
    if HTTPS_PROXY:
        logger.info("Using proxy: %s", HTTPS_PROXY)
        from telegram.request import HTTPXRequest
        builder = builder.request(
            HTTPXRequest(
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
                pool_timeout=30,
                proxy=HTTPS_PROXY,
            )
        )

    app = builder.build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.VOICE | filters.CONTACT) & ~filters.COMMAND,
        handle_message
    ))

    # Documents & photos (lab reports, scans, prescriptions)
    from app.bot.documents import handle_document_message
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_document_message))

    # Error handler for network issues
    async def error_handler(update, context):
        """Handle errors gracefully - especially transient network issues."""
        import telegram.error
        err = context.error
        if isinstance(err, telegram.error.NetworkError):
            logger.warning(f"⚠️ Network error (will retry automatically): {err}")
        elif isinstance(err, telegram.error.RetryAfter):
            logger.warning(f"⚠️ Rate limited, retrying after {err.retry_after}s")
        elif isinstance(err, telegram.error.TimedOut):
            logger.warning(f"⚠️ Request timed out (will retry): {err}")
        else:
            logger.error(f"❌ Unhandled error: {err}", exc_info=context.error)

    app.add_error_handler(error_handler)

    # Start appointment webhook Flask server in a background thread
    try:
        import threading
        from appointment.webhook_server import run_appointment_webhook, set_bot_app as set_appt_bot
        set_appt_bot(app)  # Inject bot reference for Telegram notifications
        appt_thread = threading.Thread(target=run_appointment_webhook, daemon=True)
        appt_thread.start()
        logger.info("Appointment webhook server started (port 5050)")
    except Exception as appt_err:
        logger.warning("Appointment webhook failed to start: %s", appt_err)

    # Start polling with retries and drop_pending_updates
    # bootstrap_retries=-1 means infinite retries until connection succeeds
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )


if __name__ == '__main__':
    main()
