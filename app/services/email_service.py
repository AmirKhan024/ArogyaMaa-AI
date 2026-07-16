"""
Transactional email via Brevo SMTP.

Flask-free on purpose: this module is used both by the web app and by the
standalone Telegram bot process (appointment confirmations), so it must not
depend on an application context. All failures are logged and reported as a
boolean — email is never allowed to take down a user-facing flow.

Required env vars:
    BREVO_SMTP_LOGIN, BREVO_SMTP_KEY
Optional:
    BREVO_SMTP_HOST (default smtp-relay.brevo.com), BREVO_SMTP_PORT (default 587),
    EMAIL_FROM (default = BREVO_SMTP_LOGIN), EMAIL_FROM_NAME (default "ArogyaMaa")
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("BREVO_SMTP_PORT", "587"))
SMTP_LOGIN = os.getenv("BREVO_SMTP_LOGIN")
SMTP_KEY = os.getenv("BREVO_SMTP_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM") or SMTP_LOGIN
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "ArogyaMaa")


def is_configured() -> bool:
    """True when the SMTP credentials needed to send are present."""
    return bool(SMTP_LOGIN and SMTP_KEY and EMAIL_FROM)


def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    Send an HTML email (with optional plain-text alternative).

    Returns True on success, False on any failure (logged, never raised).
    """
    if not to:
        logger.warning("[Email] No recipient given; skipping send")
        return False
    if not is_configured():
        logger.warning(
            "[Email] Brevo SMTP not configured (BREVO_SMTP_LOGIN/BREVO_SMTP_KEY/EMAIL_FROM); "
            "skipping send to %s", to
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((EMAIL_FROM_NAME, EMAIL_FROM))
    msg["To"] = to
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_KEY)
            server.sendmail(EMAIL_FROM, [to], msg.as_string())
        logger.info("[Email] Sent '%s' to %s", subject, to)
        return True
    except Exception as exc:
        logger.error("[Email] Failed to send '%s' to %s: %s", subject, to, exc)
        return False
