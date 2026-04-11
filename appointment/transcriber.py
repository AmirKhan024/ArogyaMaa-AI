"""
Speech-to-Text module using OpenAI Whisper API.

Transcribes Telegram voice messages (.oga files) to text.
The model is called REMOTELY — nothing is downloaded locally.

Adapted from voice_appointment_bot/stt/transcriber.py.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "hi")

_openai_client = None


def _get_client():
    """Lazy-initialise and return the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set in .env. "
                "Get a key at https://platform.openai.com/api-keys"
            )
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialised for Whisper STT (appointment module).")
    return _openai_client


def transcribe_audio(oga_path: str) -> str:
    """
    Transcribes a Telegram voice file (.oga) using the OpenAI Whisper API.

    Args:
        oga_path: Path to the downloaded .oga file from Telegram.

    Returns:
        Transcribed text as a string.
    """
    client = _get_client()

    logger.info(f"[Appointment STT] Sending audio to Whisper: {oga_path}")

    with open(oga_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            language=WHISPER_LANGUAGE,
            response_format="text",
        )

    text = response.strip() if isinstance(response, str) else str(response).strip()

    if not text:
        raise RuntimeError("Whisper API returned empty transcription.")

    logger.info(f"[Appointment STT] Transcription: '{text}'")
    return text
