"""
Speech-to-Text module using Groq Whisper (FREE tier).

Transcribes Telegram voice messages (.oga files) to text via the Groq API — the same
free approach used by app/ai/registration/voice_processor.py. Nothing runs locally.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "hi")

_groq_client = None


def _get_client():
    """Lazy-initialise and return the Groq client."""
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set in .env. Get a free key at https://console.groq.com"
            )
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialised for Whisper STT (appointment module).")
    return _groq_client


def transcribe_audio(oga_path: str) -> str:
    """
    Transcribe a Telegram voice file (.oga) using Groq Whisper.

    Args:
        oga_path: Path to the downloaded .oga file from Telegram.

    Returns:
        Transcribed text as a string.
    """
    client = _get_client()

    logger.info(f"[Appointment STT] Sending audio to Groq Whisper: {oga_path}")

    with open(oga_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=(os.path.basename(oga_path), audio_file.read()),
            language=WHISPER_LANGUAGE,
            response_format="text",
        )

    text = response.strip() if isinstance(response, str) else str(response).strip()

    if not text:
        raise RuntimeError("Groq Whisper returned empty transcription.")

    logger.info(f"[Appointment STT] Transcription: '{text}'")
    return text
