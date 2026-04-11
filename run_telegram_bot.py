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
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import logging
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
from pymongo import MongoClient
from bson import ObjectId
from groq import Groq

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
MONGO_URI = os.getenv('MONGODB_URI', os.getenv('MONGO_URI', 'mongodb://localhost:27017'))
DB_NAME = os.getenv('MONGODB_DB_NAME', os.getenv('DB_NAME', 'ArogyaMaa'))
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
# Optional: set HTTPS_PROXY in .env if Telegram is blocked in your region
# Example: HTTPS_PROXY=http://127.0.0.1:1080 or HTTPS_PROXY=socks5://127.0.0.1:1080
HTTPS_PROXY = os.getenv('HTTPS_PROXY', os.getenv('https_proxy', ''))

# MongoDB Connection
mongo_client = None
db = None
mothers_collection = None
messages_collection = None
assessments_collection = None
registration_sessions = None

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    mothers_collection = db['mothers']
    messages_collection = db['messages']
    assessments_collection = db['assessments']
    registration_sessions = db['registration_sessions']
    # Test connection
    mongo_client.server_info()
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    mongo_client = None
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

# Ensure tmp directory exists for voice processing
os.makedirs('tmp', exist_ok=True)


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
    """Handle /start command - Always show main menu with 6 buttons."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    if db is None:
        await update.message.reply_text("❌ Database connection error. Please try again later.")
        return

    # Check if mother already registered
    existing_mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})

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

        mothers_collection.insert_one(mother_data)
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

    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})

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
        from appointment.handler import start_appointment_flow
        await start_appointment_flow(update, context)
    elif callback_data == 'menu_register':
        await handle_register_button(update, context)


async def show_health_summary(chat_id, query):
    """Show latest health assessment and AI summary."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return

    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    if not mother:
        await query.edit_message_text("Please use /start first.")
        return

    assessments = list(assessments_collection.find(
        {'mother_id': mother['_id']}
    ).sort('timestamp', -1).limit(1))

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

    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    if not mother:
        await query.edit_message_text("Please use /start first.")
        return

    recent_messages = list(messages_collection.find(
        {'mother_id': mother['_id'], 'message_type': {'$ne': 'from_mother'}}
    ).sort('timestamp', -1).limit(5))

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
            timestamp = msg.get('timestamp', datetime.now(timezone.utc))
            message += f"*{sender}* ({timestamp.strftime('%b %d, %H:%M')})\n{content}\n\n"
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


# ==================== AI REGISTRATION HANDLERS ====================

async def handle_register_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 📝 Register button - start AI-driven registration."""
    query = update.callback_query
    chat_id = query.message.chat.id

    if not reg_engine:
        await query.message.reply_text("⚠️ Registration service is temporarily unavailable.")
        return

    # Check if already completed full registration
    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    if mother and mother.get('registration_complete'):
        await query.message.reply_text("✅ You are already registered! Use /start to access all features.")
        return

    # Get or create registration session
    session = registration_sessions.find_one({"telegram_chat_id": str(chat_id)})
    if not session:
        full_name = mother['name'] if mother else (query.from_user.first_name or 'Mother')
        session = {
            "telegram_chat_id": str(chat_id),
            "full_name": full_name,
            "registration_active": True,
        }
        registration_sessions.update_one(
            {"telegram_chat_id": str(chat_id)},
            {"$set": session},
            upsert=True
        )

    # Ensure registration is marked active
    if not session.get('registration_active'):
        registration_sessions.update_one(
            {"telegram_chat_id": str(chat_id)},
            {"$set": {"registration_active": True}}
        )
        session['registration_active'] = True

    # Get first (or next) question from AI engine
    _, next_q_text, is_comp, ui_details = reg_engine.provide_next_question(session)

    if is_comp:
        # Edge case: session was already complete
        _finalize_polling_registration(str(chat_id))
        await query.message.reply_text(next_q_text, reply_markup=ReplyKeyboardRemove())
        return

    await query.message.reply_text(
        next_q_text,
        reply_markup=get_registration_keyboard(ui_details)
    )
    await send_voice_response(query.message, context, next_q_text, session)


async def handle_registration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process text/voice/contact input during active AI registration."""
    chat_id = update.effective_chat.id
    session = registration_sessions.find_one({"telegram_chat_id": str(chat_id)})

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
            ogg_path = f"tmp/{update.message.voice.file_id}.ogg"
            await voice_file.download_to_drive(ogg_path)
            text_content = voice_processor.audio_to_text(ogg_path)
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

    # Run the AI registration engine
    extracted, next_q_text, is_comp, ui_details = reg_engine.provide_next_question(session, text_content)

    # Update session data
    if extracted:
        registration_sessions.update_one(
            {"telegram_chat_id": str(chat_id)},
            {"$set": extracted}
        )

    # Refresh session for language detection
    new_session = registration_sessions.find_one({"telegram_chat_id": str(chat_id)})

    if is_comp:
        # Registration complete
        _finalize_polling_registration(str(chat_id))

        user_lang = new_session.get('preferred_language', 'Hindi')
        if 'English' in str(user_lang):
            final_msg = "✅ Registration Complete! Your health profile is now active. We will monitor your symptoms and notify your ASHA worker if needed."
        else:
            final_msg = "✅ पंजीकरण पूरा हुआ! आपका स्वास्थ्य प्रोफाइल अब सक्रिय है। हम आपके लक्षणों पर नजर रखेंगे और जरूरत पड़ने पर आपकी आशा वर्कर को सूचित करेंगे।"

        await update.message.reply_text(final_msg, reply_markup=ReplyKeyboardRemove())
        await send_voice_response(update.message, context, final_msg, new_session)

        logger.info(f"✅ AI Registration completed for chat_id: {chat_id}")
    else:
        await update.message.reply_text(
            next_q_text,
            reply_markup=get_registration_keyboard(ui_details)
        )
        await send_voice_response(update.message, context, next_q_text, new_session)

    return True


def _finalize_polling_registration(telegram_chat_id):
    """Move registration session data into mothers collection (polling mode)."""
    session = registration_sessions.find_one({"telegram_chat_id": telegram_chat_id})
    if not session:
        return False

    update_data = {
        'registration_complete': True,
        'registration_source': 'ai_bot',
        'registration_completed_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }

    # Map session fields to mother schema
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
    if session.get('gestational_week'):
        update_data['gestational_age'] = session['gestational_week']
    if session.get('edd_date'):
        update_data['edd'] = session['edd_date']

    # Pregnancy data
    pregnancy_data = {}
    for field in ['gestational_week', 'lmp_date', 'edd_date', 'first_pregnancy',
                  'previous_pregnancies_count', 'fetal_movement']:
        if session.get(field):
            key = 'gestational_age_weeks' if field == 'gestational_week' else (
                'edd' if field == 'edd_date' else field)
            pregnancy_data[key] = session[field]
    if pregnancy_data:
        update_data['current_pregnancy'] = pregnancy_data

    # Medical history
    medical_data = {}
    for field in ['blood_group', 'previous_complications', 'medical_conditions',
                  'medications_supplements', 'allergies', 'major_surgeries',
                  'vaccines_received', 'scans_done', 'lab_tests_done']:
        if session.get(field):
            key = 'conditions' if field == 'medical_conditions' else field
            medical_data[key] = session[field]
    if medical_data:
        update_data['medical_history'] = medical_data

    # Health status fields
    for field in ['current_symptoms', 'danger_signs', 'substance_usage', 'doctor_consent']:
        if session.get(field):
            update_data[field] = session[field]

    # Update mothers collection
    mothers_collection.update_one(
        {"telegram_chat_id": telegram_chat_id},
        {"$set": update_data},
        upsert=True
    )

    # Clean up session
    registration_sessions.delete_one({"telegram_chat_id": telegram_chat_id})
    return True


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

        assessments = list(assessments_collection.find(
            {'mother_id': mother['_id']}
        ).sort('timestamp', -1).limit(1))

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
- Risk Level: {ai_eval.get('risk_level', 'UNKNOWN')}
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
            model="llama-3.1-8b-instant",
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
    if registration_sessions is not None:
        session = registration_sessions.find_one({"telegram_chat_id": str(chat_id)})
        if session and session.get('registration_active'):
            handled = await handle_registration_input(update, context)
            if handled:
                return

    if db is None:
        return

    message_text = update.message.text if update.message.text else ''
    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})

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
        # Regular message - save for healthcare team
        if message_text:
            message_data = {
                'mother_id': mother['_id'],
                'mother_name': mother.get('name'),
                'telegram_chat_id': str(chat_id),
                'message_type': 'from_mother',
                'content': message_text,
                'timestamp': datetime.now(timezone.utc),
                'read': False
            }
            messages_collection.insert_one(message_data)

        await update.message.reply_text(
            "📨 Message received! Your healthcare team will respond soon.\n\n"
            "For emergency situations, please call your local health center."
        )


# ==================== MAIN ====================

def main():
    """Start the bot in polling mode."""
    if not BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not found in .env file")
        return

    if db is None:
        print("❌ ERROR: MongoDB connection failed")
        return

    print(f"✅ Bot token found: {BOT_TOKEN[:10]}...")
    print("✅ MongoDB connected")
    if reg_engine:
        print("✅ AI Registration Engine ready")
    if voice_processor:
        print("✅ Voice Processor ready (STT + TTS)")
    print("🚀 Starting Telegram bot...")
    print("\nBot is running! Press Ctrl+C to stop.\n")

    # Pre-flight connectivity check
    import httpx as _httpx
    print("🔍 Checking connectivity to Telegram API...")
    try:
        _test_client = _httpx.Client(timeout=10, proxy=HTTPS_PROXY if HTTPS_PROXY else None)
        _resp = _test_client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
        _test_client.close()
        if _resp.status_code == 200:
            bot_info = _resp.json().get('result', {})
            print(f"✅ Connected to Telegram! Bot: @{bot_info.get('username', 'unknown')}")
        else:
            print(f"⚠️ Telegram API returned status {_resp.status_code}")
    except Exception as _e:
        print(f"⚠️ Cannot reach api.telegram.org: {_e}")
        print("   Possible causes:")
        print("   1. No internet connection")
        print("   2. Telegram is blocked by your ISP/firewall")
        print("   3. VPN/proxy needed - set HTTPS_PROXY in .env")
        print("      Example: HTTPS_PROXY=http://127.0.0.1:1080")
        print("   Will keep retrying...")

    # Create application with increased timeouts for flaky networks
    builder = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
    )

    # Add proxy support if configured
    if HTTPS_PROXY:
        print(f"🌐 Using proxy: {HTTPS_PROXY}")
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
        from appointment.excel_manager import _ensure_workbook_exists
        _ensure_workbook_exists()  # Create Excel file if it doesn't exist
        set_appt_bot(app)  # Inject bot reference for Telegram notifications
        appt_thread = threading.Thread(target=run_appointment_webhook, daemon=True)
        appt_thread.start()
        print("✅ Appointment webhook server started (port 5050)")
    except Exception as appt_err:
        print(f"⚠️ Appointment webhook failed to start: {appt_err}")
        logger.warning(f"Appointment webhook init failed: {appt_err}")

    # Start polling with retries and drop_pending_updates
    # bootstrap_retries=-1 means infinite retries until connection succeeds
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )


if __name__ == '__main__':
    main()
