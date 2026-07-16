"""
Document / photo upload handler for the polling Telegram bot.

Mothers send lab reports, scans, and prescriptions as Telegram documents or
photos. This handler downloads the file, stores it under uploads/documents/,
creates a `documents` record, runs AI analysis (safe-fail), and notifies the
assigned ASHA worker.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes
from werkzeug.utils import secure_filename

from app.repositories import mothers_repo, messages_repo, documents_repo

logger = logging.getLogger(__name__)

# Repo root (this file lives at app/bot/documents.py)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(_REPO_ROOT, "uploads", "documents")


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a document or photo sent by a mother."""
    chat_id = update.effective_chat.id
    message = update.message
    if message is None:
        return

    mother = mothers_repo.get_by_telegram_chat_id(chat_id)
    if not mother:
        await message.reply_text("Please use /start first.")
        return

    mother_id = mother["_id"]
    mother_name = mother.get("name", "Unknown Mother")

    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if message.photo:
            # Telegram sends multiple sizes; the last is the largest.
            file_id = message.photo[-1].file_id
            filename = f"telegram_photo_{stamp}.jpg"
            file_type = "image/jpeg"
        elif message.document:
            file_id = message.document.file_id
            filename = message.document.file_name or f"telegram_doc_{stamp}"
            file_type = message.document.mime_type or "application/octet-stream"
        else:
            return

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_filename = secure_filename(filename) or f"telegram_upload_{stamp}"
        local_path = os.path.join(UPLOAD_DIR, safe_filename)

        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(local_path)
        file_size = os.path.getsize(local_path)

        document_data = {
            "mother_id": mother_id,
            "uploaded_by": "mother",
            "uploaded_by_id": mother_id,
            "uploaded_by_name": mother_name,
            "document_type": "general_document",
            "description": f"Uploaded by {mother_name} via Telegram",
            "telegram_file_id": file_id,
            "file_metadata": {
                "original_filename": filename,
                "stored_filename": safe_filename,
                "file_path": f"uploads/documents/{safe_filename}",
                "file_size_bytes": file_size,
                "file_type": file_type,
            },
            "visible_to": ["mother", "asha", "doctor", "admin"],
            "uploaded_at": datetime.now(timezone.utc),
        }
        document_id = documents_repo.create(document_data)
        logger.info(f"[Bot] Document {document_id} uploaded by mother {mother_id}")

        # AI analysis (safe-fail; sync Groq call runs off the event loop)
        ai_ok = False
        try:
            from app.ai.document_analyzer import analyze_medical_document

            await message.reply_text("⏳ Analyzing document...\n\nPlease wait a moment.")
            analysis_result = await asyncio.to_thread(
                analyze_medical_document, local_path, "general_document", ""
            )
            if analysis_result.get("success"):
                extracted = analysis_result.pop("extracted_text", "")
                documents_repo.update_ai_analysis(document_id, analysis_result)
                if extracted:
                    documents_repo.update_extracted_text(document_id, extracted)
                ai_ok = True
                logger.info(f"[Bot] AI analysis completed for document {document_id}")
        except Exception as ai_error:
            logger.error(f"[Bot] AI analysis failed: {ai_error}")

        # Notify the assigned ASHA worker (safe-fail)
        if mother.get("assigned_asha_id"):
            try:
                messages_repo.add_message(mother_id, {
                    "sender_type": "system",
                    "sender_name": "ArogyaMaa System",
                    "text": f"{mother_name} uploaded a new document via Telegram",
                    "from_mother": True,
                    "to_asha": True,
                    "to_asha_id": mother.get("assigned_asha_id"),
                    "document_id": document_id,
                    "read": False,
                })
            except Exception as e:
                logger.error(f"[Bot] Failed to notify ASHA: {e}")

        reply = (
            "✅ *Document Uploaded Successfully!*\n\n"
            "Your document has been:\n"
            "• Saved to your medical records\n"
            "• Shared with your healthcare team\n"
            f"{'• Analyzed by AI 🤖' if ai_ok else ''}\n\n"
            "Your healthcare team will review it and contact you if needed.\n\n"
            "Use /start to return to the main menu."
        )
        await message.reply_text(reply, parse_mode="Markdown")

        messages_repo.add_message(mother_id, {
            "sender_type": "mother",
            "sender_name": mother_name,
            "text": f"Uploaded document: {filename}",
        })

    except Exception as e:
        logger.error(f"[Bot] Document upload error: {e}", exc_info=True)
        await message.reply_text(
            "❌ Upload failed. Please try again or contact your ASHA worker."
        )
