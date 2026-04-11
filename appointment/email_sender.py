"""
Email sender for appointment notifications.

Sends an HTML email to the doctor with appointment details
and Confirm / Reschedule action buttons.

Adapted from voice_appointment_bot/email_module/sender.py.
"""

import smtplib
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GMAIL_SENDER = os.getenv("GMAIL_SENDER_EMAIL")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
DOCTOR_EMAIL = os.getenv("DOCTOR_EMAIL")
DOCTOR_NAME = os.getenv("DOCTOR_NAME", "Doctor")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:5050")

# Load Jinja2 template from appointment/templates/
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


def send_doctor_email(appointment: dict) -> None:
    """
    Sends an HTML email to the doctor with appointment details.

    Args:
        appointment: Full appointment dict

    Raises:
        smtplib.SMTPException: If sending fails
        ValueError: If required env vars are missing
    """
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        raise ValueError("GMAIL_SENDER_EMAIL and GMAIL_APP_PASSWORD must be set in .env")

    if not DOCTOR_EMAIL:
        raise ValueError("DOCTOR_EMAIL must be set in .env")

    confirm_url = (
        f"{WEBHOOK_BASE_URL}/appointment/confirm"
        f"?id={appointment['appointment_id']}"
        f"&token={appointment['security_token']}"
        f"&date={appointment['preferred_date']}"
        f"&time={appointment['preferred_time']}"
    )
    reschedule_url = (
        f"{WEBHOOK_BASE_URL}/appointment/reschedule"
        f"?id={appointment['appointment_id']}"
        f"&token={appointment['security_token']}"
    )

    template = jinja_env.get_template("doctor_email.html")
    html_body = template.render(
        doctor_name=DOCTOR_NAME,
        appointment=appointment,
        confirm_url=confirm_url,
        reschedule_url=reschedule_url,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"[नया अपॉइंटमेंट] {appointment['patient_name']} — "
        f"{appointment['preferred_date']} {appointment['preferred_time']}"
    )
    msg["From"] = GMAIL_SENDER
    msg["To"] = DOCTOR_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_SENDER, DOCTOR_EMAIL, msg.as_string())
        logger.info(f"[Appointment Email] Sent to {DOCTOR_EMAIL}")
