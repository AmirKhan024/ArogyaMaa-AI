"""
Email sender for appointment notifications.

Sends an HTML email to the doctor with appointment details
and Confirm / Reschedule action buttons, via the shared Brevo
SMTP service (app/services/email_service.py).
"""

import os
import logging
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

from app.services import email_service

load_dotenv()
logger = logging.getLogger(__name__)

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
        ValueError: If required env vars are missing
        RuntimeError: If the SMTP send fails
    """
    if not email_service.is_configured():
        raise ValueError("Brevo SMTP is not configured (BREVO_SMTP_LOGIN / BREVO_SMTP_KEY / EMAIL_FROM)")

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

    subject = (
        f"[नया अपॉइंटमेंट] {appointment['patient_name']} — "
        f"{appointment['preferred_date']} {appointment['preferred_time']}"
    )

    if not email_service.send_email(DOCTOR_EMAIL, subject, html_body):
        raise RuntimeError(f"Failed to send appointment email to {DOCTOR_EMAIL}")
    logger.info(f"[Appointment Email] Sent to {DOCTOR_EMAIL}")
