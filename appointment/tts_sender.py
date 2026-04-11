"""
Text-to-Speech module using HuggingFace Inference API (Voxtral).

Generates Hindi voice responses and sends them as Telegram voice messages.
The model is called REMOTELY — nothing is downloaded locally.

Adapted from voice_appointment_bot/bot/tts_sender.py.
"""

import os
import uuid
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
HF_TTS_MODEL = os.getenv("HF_TTS_MODEL", "mistralai/Voxtral-4B-TTS-2603")
TTS_LANGUAGE_HINT = os.getenv("TTS_LANGUAGE_HINT", "Hindi")
TEMP_AUDIO_DIR = os.getenv("TEMP_AUDIO_DIR", "temp_audio/")

_hf_client = None


def _get_hf_client():
    """Lazy-initialise and return the HF Inference client."""
    global _hf_client
    if _hf_client is None:
        if not HF_API_TOKEN:
            raise RuntimeError(
                "HF_API_TOKEN is not set in .env. "
                "Get a token at https://huggingface.co/settings/tokens"
            )
        from huggingface_hub import InferenceClient
        _hf_client = InferenceClient(
            model=HF_TTS_MODEL,
            token=HF_API_TOKEN,
        )
        logger.info(f"[Appointment TTS] HF client initialised: {HF_TTS_MODEL}")
    return _hf_client


def generate_tts_audio(text: str, language_hint: str = None) -> str:
    """
    Converts text to speech via HF Inference API and saves as .ogg.

    Returns:
        Path to the generated .ogg audio file.
    """
    client = _get_hf_client()

    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    hint = language_hint or TTS_LANGUAGE_HINT
    prompt = f"[{hint}] {text}"

    filename = f"appt_tts_{uuid.uuid4()}.ogg"
    filepath = os.path.join(TEMP_AUDIO_DIR, filename)

    audio_bytes: bytes = client.text_to_speech(prompt)

    if not audio_bytes:
        raise ValueError("HF Inference API returned empty audio bytes.")

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"[Appointment TTS] Audio generated: {filepath}")
    return filepath


async def send_voice_reply(update, context, text: str, language_hint: str = None) -> None:
    """
    Generates TTS and sends it as a voice message.
    Falls back to text-only if TTS fails.
    """
    audio_path = None
    try:
        audio_path = generate_tts_audio(text, language_hint)
        with open(audio_path, "rb") as audio_file:
            if update.callback_query:
                # Called from a callback — send to the chat directly
                chat_id = update.effective_chat.id
                await context.bot.send_voice(chat_id=chat_id, voice=audio_file, caption=text[:1024])
            elif update.message:
                await update.message.reply_voice(voice=audio_file, caption=text[:1024])
            else:
                chat_id = update.effective_chat.id
                await context.bot.send_voice(chat_id=chat_id, voice=audio_file, caption=text[:1024])
    except Exception as e:
        logger.error(f"[Appointment TTS] Failed, sending text fallback: {e}")
        # Fallback: send as text
        if update.effective_message:
            await update.effective_message.reply_text(text)
        elif update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


async def send_voice_to_chat(bot, chat_id: int, audio_path: str) -> None:
    """
    Sends a pre-generated audio file to a specific chat_id.
    Used by the webhook to notify patients after doctor confirmation.
    """
    try:
        with open(audio_path, "rb") as audio_file:
            await bot.send_voice(chat_id=chat_id, voice=audio_file)
        logger.info(f"[Appointment TTS] Voice sent to chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"[Appointment TTS] Failed to send voice to {chat_id}: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
