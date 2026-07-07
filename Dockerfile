# ArogyaMaa-AI — web + bot share this image (compose picks the command per service).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg is required by pydub for the Edge-TTS / Whisper voice audio conversion.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first so the layer caches when only app code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Flask web server (see docker-compose.yml for the bot service).
EXPOSE 8000
CMD ["python", "run.py"]
