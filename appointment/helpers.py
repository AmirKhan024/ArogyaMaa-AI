"""
Appointment Helpers — utility functions.

Adapted from voice_appointment_bot/utils/helpers.py.
"""

import re
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Removes characters unsafe for filenames."""
    return re.sub(r'[^\w\-_\. ]', '_', name)


def ensure_dir(path: str) -> None:
    """Creates directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def current_iso_timestamp() -> str:
    """Returns current datetime in ISO format."""
    return datetime.now().isoformat(timespec="seconds")


def validate_phone(phone: str) -> bool:
    """Returns True if phone is a valid 10-digit Indian mobile number."""
    return bool(re.fullmatch(r'[6-9]\d{9}', phone))


def validate_date_format(date_str: str) -> bool:
    """Returns True if date matches DD-MM-YYYY format."""
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False


def validate_time_format(time_str: str) -> bool:
    """Returns True if time matches HH:MM format."""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False
