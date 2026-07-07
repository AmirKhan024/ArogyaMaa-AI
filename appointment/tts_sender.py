"""
Text-to-Speech module using Edge-TTS (FREE, no API key).

Generates Hindi voice responses and sends them as Telegram voice messages, mirroring
the free registration voice path (app/ai/registration/voice_processor.py):
Edge-TTS neural voice -> MP3 -> OGG/opus (pydub). Nothing paid, no HF token.
"""

import os
import re
import uuid
import logging

import edge_tts
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TTS_LANGUAGE_HINT = os.getenv("TTS_LANGUAGE_HINT", "Hindi")
TEMP_AUDIO_DIR = os.getenv("TEMP_AUDIO_DIR", "temp_audio/")

# Neural voices per language hint.
_VOICES = {
    "hindi": "hi-IN-SwaraNeural",
    "marathi": "mr-IN-AarohiNeural",
    "english": "en-IN-NeerjaNeural",
}


def _voice_for(language_hint: str) -> str:
    return _VOICES.get((language_hint or TTS_LANGUAGE_HINT).strip().lower(), _VOICES["hindi"])


async def generate_tts_audio(text: str, language_hint: str = None) -> str:
    """
    Convert text to speech via Edge-TTS and return the path to an OGG/opus file
    suitable for a Telegram voice note.
    """
    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    # Strip simple markdown so it isn't read aloud.
    clean = re.sub(r"[*_`#]+", "", text or "").strip()
    voice = _voice_for(language_hint)

    base = os.path.join(TEMP_AUDIO_DIR, f"appt_tts_{uuid.uuid4()}")
    mp3_path = base + ".mp3"
    ogg_path = base + ".ogg"

    communicate = edge_tts.Communicate(clean, voice)
    await communicate.save(mp3_path)

    # Convert MP3 -> OGG (opus) for Telegram voice notes.
    AudioSegment.from_mp3(mp3_path).export(ogg_path, format="ogg", codec="libopus")
    if os.path.exists(mp3_path):
        os.remove(mp3_path)

    logger.info(f"[Appointment TTS] Audio generated: {ogg_path}")
    return ogg_path


async def send_voice_reply(update, context, text: str, language_hint: str = None) -> None:
    """
    Generate TTS and send it as a Telegram voice message.
    Falls back to text-only if TTS fails.
    """
    audio_path = None
    try:
        audio_path = await generate_tts_audio(text, language_hint)
        with open(audio_path, "rb") as audio_file:
            if update.callback_query:
                chat_id = update.effective_chat.id
                await context.bot.send_voice(chat_id=chat_id, voice=audio_file, caption=text[:1024])
            elif update.message:
                await update.message.reply_voice(voice=audio_file, caption=text[:1024])
            else:
                chat_id = update.effective_chat.id
                await context.bot.send_voice(chat_id=chat_id, voice=audio_file, caption=text[:1024])
    except Exception as e:
        logger.error(f"[Appointment TTS] Failed, sending text fallback: {e}")
        if update.effective_message:
            await update.effective_message.reply_text(text)
        elif update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


async def send_voice_to_chat(bot, chat_id: int, audio_path: str) -> None:
    """
    Send a pre-generated audio file to a specific chat_id.
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
