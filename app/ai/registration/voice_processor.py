"""
Voice Processor for Registration

Handles Speech-to-Text (Groq Whisper) and Text-to-Speech (Edge-TTS)
for voice-enabled registration flow.
"""

import os
import logging
import edge_tts
from pydub import AudioSegment
from groq import Groq

logger = logging.getLogger(__name__)

# Ensure there's a temp dir for audio processing
temp_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'tmp')
os.makedirs(temp_dir, exist_ok=True)


class VoiceProcessor:
    def __init__(self, groq_api_key: str = None):
        if groq_api_key:
            self.groq_client = Groq(api_key=groq_api_key)
        else:
            self.groq_client = None

    def audio_to_text(self, ogg_file_path: str, language: str | None = None) -> str:
        """
        Converts an OGG voice note to text using Groq Whisper.

        ``language`` is an ISO-639-1 hint ('hi', 'en', 'mr', ...). When None,
        Whisper auto-detects the spoken language instead of assuming Hindi.
        """
        if not self.groq_client:
            return "Please provide a valid GROQ API KEY to use the voice feature."

        try:
            kwargs = {
                "model": os.getenv("WHISPER_MODEL", "whisper-large-v3"),
                "prompt": "Indian pregnancy health terminology",
                "response_format": "json",
                "temperature": 0.0,
            }
            if language:
                kwargs["language"] = language
            with open(ogg_file_path, "rb") as file:
                translation = self.groq_client.audio.transcriptions.create(
                    file=(os.path.basename(ogg_file_path), file.read()),
                    **kwargs,
                )
            return translation.text
        except Exception as e:
            logger.error(f"Error in Groq STT: {e}")
            return "Could not understand audio clearly."

    async def text_to_audio(self, text: str, lang: str = 'hi') -> str:
        """Converts text to audio (Voice) using Edge-TTS (Free Neural Voices)."""
        import re
        # Clean text of markdown characters which can break TTS
        text = re.sub(r'[*_#~]', '', text).strip()
        if not text:
            return None

        try:
            # Map languages to premium neural voices
            voice = "hi-IN-SwaraNeural"
            if lang and 'marathi' in lang.lower():
                voice = "mr-IN-AarohiNeural"
            elif lang and 'english' in lang.lower():
                voice = "en-IN-NeerjaNeural"

            output_path = os.path.join(temp_dir, f"response_{os.urandom(4).hex()}.mp3")

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)

            # Convert to OGG for Telegram Voice Note compatibility
            audio = AudioSegment.from_mp3(output_path)
            ogg_path = output_path.replace(".mp3", ".ogg")
            audio.export(ogg_path, format="ogg", codec="libopus")

            # Cleanup mp3
            if os.path.exists(output_path):
                os.remove(output_path)

            return ogg_path
        except Exception as e:
            logger.error(f"Error in Edge-TTS: {e}")
            return None
