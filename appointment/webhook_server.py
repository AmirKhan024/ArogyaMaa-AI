"""
Appointment Webhook Server

Flask server for doctor to confirm/reschedule appointments via email links.
Runs on a separate port (5050 by default) in a background daemon thread.

All routes are prefixed with /appointment/ to avoid conflicts with
the main ArogyaMaa Flask app (port 8000).

Adapted from voice_appointment_bot/webhook/server.py.
"""

import os
import logging
import asyncio
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

appt_flask_app = Flask(__name__)

# Reference to the running Telegram bot application (set from run_telegram_bot.py)
_bot_app_ref = None


def set_bot_app(bot_app):
    """Called from main to inject the running bot application."""
    global _bot_app_ref
    _bot_app_ref = bot_app


# ── Inline HTML templates ─────────────────────────────────────────────────────

CONFIRM_SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head><meta charset="UTF-8"><title>पुष्टि हो गई</title>
<style>
  body { font-family: Arial, sans-serif; display: flex; justify-content: center;
         align-items: center; height: 100vh; background: #f0fff4; margin: 0; }
  .box { background: white; border-radius: 12px; padding: 40px; text-align: center;
         box-shadow: 0 4px 16px rgba(0,0,0,0.1); max-width: 400px; }
  .icon { font-size: 48px; }
  h2 { color: #28a745; }
</style></head>
<body><div class="box">
  <div class="icon">✅</div>
  <h2>अपॉइंटमेंट पुष्टि हो गई!</h2>
  <p>मरीज़ को Telegram पर सूचना भेज दी गई है।</p>
  <p style="color:#999; font-size:13px;">आप यह विंडो बंद कर सकते हैं।</p>
</div></body></html>
"""

RESCHEDULE_FORM_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head><meta charset="UTF-8"><title>नई तारीख चुनें</title>
<style>
  body { font-family: Arial, sans-serif; display: flex; justify-content: center;
         align-items: center; min-height: 100vh; background: #fff8f0; margin: 0; }
  .box { background: white; border-radius: 12px; padding: 40px; max-width: 450px;
         width: 90%; box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
  h2 { color: #fd7e14; margin-top: 0; }
  label { display: block; margin: 16px 0 6px; font-weight: bold; }
  input, textarea { width: 100%; padding: 10px; border: 1px solid #ddd;
                    border-radius: 6px; font-size: 15px; box-sizing: border-box; }
  .submit-btn { background: #fd7e14; color: white; border: none; padding: 14px 24px;
                border-radius: 6px; font-size: 16px; cursor: pointer; width: 100%;
                margin-top: 20px; }
  .submit-btn:hover { background: #e06910; }
</style></head>
<body><div class="box">
  <h2>🔄 नई तारीख और समय चुनें</h2>
  <p>मरीज़ <strong>{{ patient_name }}</strong> के लिए नई अपॉइंटमेंट तारीख और समय दर्ज करें।</p>
  <form method="POST" action="/appointment/reschedule/submit">
    <input type="hidden" name="appointment_id" value="{{ appointment_id }}">
    <input type="hidden" name="security_token" value="{{ security_token }}">
    <label>नई तारीख (DD-MM-YYYY)</label>
    <input type="text" name="new_date" placeholder="जैसे: 20-08-2025" required>
    <label>नया समय (HH:MM, 24-घंटे)</label>
    <input type="text" name="new_time" placeholder="जैसे: 10:30" required>
    <label>डॉक्टर की टिप्पणी (वैकल्पिक)</label>
    <textarea name="notes" rows="3" placeholder="यदि कोई विशेष निर्देश हो..."></textarea>
    <button type="submit" class="submit-btn">✅ पुष्टि करें</button>
  </form>
</div></body></html>
"""

RESCHEDULE_SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="hi"><head><meta charset="UTF-8"><title>अपडेट हो गया</title>
<style>body{font-family:Arial,sans-serif;display:flex;justify-content:center;align-items:center;
height:100vh;background:#f0fff4;margin:0;}
.box{background:white;border-radius:12px;padding:40px;text-align:center;
box-shadow:0 4px 16px rgba(0,0,0,0.1);max-width:400px;}h2{color:#28a745;}</style>
</head><body><div class="box"><div style="font-size:48px">🔄</div>
<h2>नया समय तय हो गया!</h2>
<p>मरीज़ को Telegram पर नई जानकारी भेज दी गई है।</p>
<p style="color:#999;font-size:13px;">आप यह विंडो बंद कर सकते हैं।</p>
</div></body></html>
"""

ERROR_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Error</title></head>
<body><h2 style="color:red;font-family:Arial">❌ त्रुटि: अपॉइंटमेंट नहीं मिला या लिंक अमान्य है।</h2>
<p>कृपया मरीज़ को Telegram के माध्यम से संपर्क करें।</p></body></html>
"""


# ── Routes (all prefixed with /appointment/) ──────────────────────────────────

@appt_flask_app.route("/appointment/confirm", methods=["GET"])
def confirm():
    """Doctor confirms appointment via email link."""
    from appointment.excel_manager import update_appointment_status

    appointment_id = request.args.get("id", "")
    security_token = request.args.get("token", "")
    confirmed_date = request.args.get("date", "")
    confirmed_time = request.args.get("time", "")

    if not all([appointment_id, security_token]):
        return ERROR_HTML, 400

    updated = update_appointment_status(
        appointment_id=appointment_id,
        security_token=security_token,
        new_status="Confirmed",
        confirmed_date=confirmed_date,
        confirmed_time=confirmed_time,
    )

    if not updated:
        return ERROR_HTML, 404

    _notify_patient_confirmed(updated)
    return CONFIRM_SUCCESS_HTML, 200


@appt_flask_app.route("/appointment/reschedule", methods=["GET"])
def reschedule_form():
    """Doctor clicks reschedule — shows form."""
    from appointment.excel_manager import get_appointment_by_id

    appointment_id = request.args.get("id", "")
    security_token = request.args.get("token", "")

    if not all([appointment_id, security_token]):
        return ERROR_HTML, 400

    appointment = get_appointment_by_id(appointment_id)
    if not appointment or appointment.get("security_token") != security_token:
        return ERROR_HTML, 404

    html = RESCHEDULE_FORM_HTML.replace("{{ patient_name }}", appointment.get("patient_name", ""))
    html = html.replace("{{ appointment_id }}", appointment_id)
    html = html.replace("{{ security_token }}", security_token)
    return html, 200


@appt_flask_app.route("/appointment/reschedule/submit", methods=["POST"])
def reschedule_submit():
    """Doctor submits new date/time."""
    from appointment.excel_manager import update_appointment_status

    appointment_id = request.form.get("appointment_id", "")
    security_token = request.form.get("security_token", "")
    new_date = request.form.get("new_date", "").strip()
    new_time = request.form.get("new_time", "").strip()
    notes = request.form.get("notes", "").strip()

    if not all([appointment_id, security_token, new_date, new_time]):
        return ERROR_HTML, 400

    updated = update_appointment_status(
        appointment_id=appointment_id,
        security_token=security_token,
        new_status="Rescheduled",
        confirmed_date=new_date,
        confirmed_time=new_time,
        doctor_notes=notes,
    )

    if not updated:
        return ERROR_HTML, 404

    _notify_patient_rescheduled(updated)
    return RESCHEDULE_SUCCESS_HTML, 200


@appt_flask_app.route("/appointment/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "ok", "service": "appointment_webhook"}), 200


# ── Patient Notification Helpers ──────────────────────────────────────────────

def _notify_patient_confirmed(appointment: dict):
    """Sends a confirmation voice/text to the patient via Telegram."""
    chat_id = appointment.get("telegram_chat_id")
    if not chat_id or not _bot_app_ref:
        logger.warning("[Appointment Webhook] Cannot notify — no chat_id or bot_app_ref")
        return

    msg = (
        f"नमस्ते {appointment.get('patient_name', '')} जी! "
        f"आपका अपॉइंटमेंट पुष्टि हो गया है। "
        f"तारीख: {appointment.get('confirmed_date', '')}। "
        f"समय: {appointment.get('confirmed_time', '')} बजे। "
        "कृपया समय पर आएं। धन्यवाद!"
    )

    _send_text_to_patient(chat_id, msg)


def _notify_patient_rescheduled(appointment: dict):
    """Sends a reschedule notification to the patient."""
    chat_id = appointment.get("telegram_chat_id")
    if not chat_id or not _bot_app_ref:
        logger.warning("[Appointment Webhook] Cannot notify — no chat_id or bot_app_ref")
        return

    notes_part = ""
    if appointment.get("doctor_notes"):
        notes_part = f"डॉक्टर का संदेश: {appointment['doctor_notes']}। "

    msg = (
        f"नमस्ते {appointment.get('patient_name', '')} जी! "
        f"आपकी अपॉइंटमेंट में बदलाव किया गया है। "
        f"नई तारीख: {appointment.get('confirmed_date', '')}। "
        f"नया समय: {appointment.get('confirmed_time', '')} बजे। "
        f"{notes_part}"
        "कृपया इस समय पर आएं। धन्यवाद!"
    )

    _send_text_to_patient(chat_id, msg)


def _send_text_to_patient(chat_id, text: str):
    """Send a text message to patient from webhook context (sync → async bridge)."""
    if not _bot_app_ref:
        return
    try:
        loop = None
        if hasattr(_bot_app_ref, 'updater') and _bot_app_ref.updater:
            loop = getattr(_bot_app_ref.updater, '_loop', None)

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    _bot_app_ref.bot.send_message(chat_id=int(chat_id), text=text)
                )
                return

        future = asyncio.run_coroutine_threadsafe(
            _bot_app_ref.bot.send_message(chat_id=int(chat_id), text=text),
            loop,
        )
        future.result(timeout=15)
    except Exception as e:
        logger.error(f"[Appointment Webhook] Failed to send message to {chat_id}: {e}")


def run_appointment_webhook():
    """Starts the appointment webhook Flask server. Called in a daemon thread."""
    port = int(os.getenv("APPOINTMENT_WEBHOOK_PORT", "5050"))
    logger.info(f"[Appointment Webhook] Starting on port {port}")
    appt_flask_app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
