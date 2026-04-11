"""
Appointment State Machine

Defines the states, field order, prompts, and parsers for the
voice appointment booking flow.

Adapted from voice_appointment_bot/bot/state_machine.py.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Try to import dateparser — graceful fallback if not installed
try:
    import dateparser
    _HAS_DATEPARSER = True
except ImportError:
    _HAS_DATEPARSER = False
    logger.warning("dateparser not installed — date/time parsing will use raw input")


# ─── State constants ───────────────────────────────────────────────────────────
# These are plain integers used as keys in context.user_data['appointment_state']

class APPT_STATES:
    """Integer state identifiers for the appointment flow."""
    ASK_NAME     = 100   # Offset from 0 to avoid collision with any other state
    ASK_AGE      = 101
    ASK_PHONE    = 102
    ASK_DATE     = 103
    ASK_TIME     = 104
    ASK_SYMPTOMS = 105


# Full field order (all 6 steps) — used when mother is NOT registered
FULL_FIELD_ORDER = [
    APPT_STATES.ASK_NAME,
    APPT_STATES.ASK_AGE,
    APPT_STATES.ASK_PHONE,
    APPT_STATES.ASK_DATE,
    APPT_STATES.ASK_TIME,
    APPT_STATES.ASK_SYMPTOMS,
]

# Short field order (3 steps) — used when mother IS registered (name/age/phone pre-filled)
SHORT_FIELD_ORDER = [
    APPT_STATES.ASK_DATE,
    APPT_STATES.ASK_TIME,
    APPT_STATES.ASK_SYMPTOMS,
]


# ─── Maps state → user_data key ───────────────────────────────────────────────

STATE_TO_KEY = {
    APPT_STATES.ASK_NAME:     "patient_name",
    APPT_STATES.ASK_AGE:      "patient_age",
    APPT_STATES.ASK_PHONE:    "patient_phone",
    APPT_STATES.ASK_DATE:     "preferred_date",
    APPT_STATES.ASK_TIME:     "preferred_time",
    APPT_STATES.ASK_SYMPTOMS: "symptoms",
}


# ─── Hindi voice prompts ──────────────────────────────────────────────────────

STATE_PROMPTS = {
    APPT_STATES.ASK_NAME: (
        "कृपया अपना पूरा नाम बताएं।"
    ),
    APPT_STATES.ASK_AGE: (
        "आपकी उम्र क्या है?"
    ),
    APPT_STATES.ASK_PHONE: (
        "आपका मोबाइल नंबर क्या है?"
    ),
    APPT_STATES.ASK_DATE: (
        "आप किस तारीख को अपॉइंटमेंट चाहते हैं? "
        "जैसे: पंद्रह अगस्त, या कल, या परसों।"
    ),
    APPT_STATES.ASK_TIME: (
        "आप किस समय आना चाहते हैं? "
        "जैसे: सुबह दस बजे, या दोपहर दो बजे।"
    ),
    APPT_STATES.ASK_SYMPTOMS: (
        "आपको क्या तकलीफ हो रही है? "
        "कृपया अपने लक्षण बताएं।"
    ),
}


def get_prompt_for_state(state: int) -> str:
    """Returns the Hindi voice prompt for the given state."""
    return STATE_PROMPTS.get(state, "कृपया जानकारी दें।")


def get_state_key(state: int) -> str:
    """Returns the user_data dictionary key for the given state."""
    return STATE_TO_KEY.get(state, "unknown")


def get_next_state(current_state: int, field_order: list) -> int | None:
    """Returns the next state integer, or None if all fields are done."""
    try:
        idx = field_order.index(current_state)
        if idx + 1 < len(field_order):
            return field_order[idx + 1]
    except ValueError:
        pass
    return None


# ─── Parsers ───────────────────────────────────────────────────────────────────

def parse_date(raw: str) -> str:
    """
    Parses a date from natural language (Hindi or English).
    Returns date as "DD-MM-YYYY" string, or the raw string if parsing fails.
    """
    if not _HAS_DATEPARSER:
        return raw
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
        "DATE_ORDER": "DMY",
    }
    parsed = dateparser.parse(raw, languages=["hi", "en"], settings=settings)
    if parsed:
        return parsed.strftime("%d-%m-%Y")
    return raw


def parse_time(raw: str) -> str:
    """
    Parses a time from natural language.
    Returns "HH:MM" in 24h format, or raw if parsing fails.
    """
    if not _HAS_DATEPARSER:
        return raw
    parsed = dateparser.parse(raw, languages=["hi", "en"])
    if parsed:
        return parsed.strftime("%H:%M")
    return raw


def parse_age(raw: str) -> str:
    """Extracts numeric age from a string."""
    numbers = re.findall(r'\d+', raw)
    if numbers:
        return numbers[0]
    return raw


def parse_phone(raw: str) -> str:
    """Extracts a 10-digit Indian mobile number from spoken text."""
    digits = re.sub(r'\D', '', raw)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


# Map state → parser function
STATE_PARSERS = {
    APPT_STATES.ASK_AGE:  parse_age,
    APPT_STATES.ASK_PHONE: parse_phone,
    APPT_STATES.ASK_DATE:  parse_date,
    APPT_STATES.ASK_TIME:  parse_time,
}
