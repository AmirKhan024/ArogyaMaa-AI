"""
Polling-bot handler tests with faked telegram Update/Context objects.

These exercise the pure-Python paths of run_telegram_bot.py (routing, timestamp
formatting, language mapping) without touching the network. DB-dependent
handlers are tested against the live DATABASE_URL when configured.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import load_dotenv

load_dotenv()

import run_telegram_bot as bot  # noqa: E402


# ── Pure helpers ───────────────────────────────────────────────────────────────

def test_lang_code_mapping():
    assert bot._lang_code("Hindi") == "hi"
    assert bot._lang_code("हिंदी") == "hi"
    assert bot._lang_code("English") == "en"
    assert bot._lang_code("Marathi") == "mr"
    assert bot._lang_code(None) is None
    assert bot._lang_code("Bengali") is None  # unknown -> Whisper auto-detect


def test_fmt_ts_accepts_datetime_iso_string_and_none():
    dt = datetime(2026, 7, 16, 14, 30, tzinfo=timezone.utc)
    assert bot._fmt_ts(dt) == "Jul 16, 14:30"
    # ISO string (what a JSONB round-trip returns) must NOT crash — this was bug #6
    assert bot._fmt_ts("2026-07-16T14:30:00+00:00") == "Jul 16, 14:30"
    assert bot._fmt_ts("2026-07-16T14:30:00Z") == "Jul 16, 14:30"
    assert bot._fmt_ts(None) == "recently"
    assert bot._fmt_ts("not-a-date") == "not-a-date"[:16]


def test_nutrition_query_detection():
    assert bot.is_nutrition_query("What should I eat for dinner?")
    assert bot.is_nutrition_query("kya main fruit kha sakti hu? can i eat mango")
    assert not bot.is_nutrition_query("My head hurts")


# ── Callback routing (all menu buttons must be wired) ─────────────────────────

@pytest.mark.asyncio
async def test_all_menu_buttons_route_to_a_handler():
    """Every callback_data in the main menu keyboard must be handled."""
    keyboard = bot.get_main_menu_keyboard().inline_keyboard
    callback_values = [btn.callback_data for row in keyboard for btn in row]
    assert set(callback_values) == {
        "health_summary", "upload_docs", "alerts", "messages",
        "send_message", "book_appointment", "menu_register",
    }

    mocks = {
        "health_summary": AsyncMock(),
        "upload_docs": AsyncMock(),
        "alerts": AsyncMock(),
        "messages": AsyncMock(),
        "send_message": AsyncMock(),
        "menu_register": AsyncMock(),
        "book_appointment": AsyncMock(),
    }

    with patch.object(bot, "show_health_summary", mocks["health_summary"]), \
         patch.object(bot, "show_upload_instructions", mocks["upload_docs"]), \
         patch.object(bot, "show_alerts", mocks["alerts"]), \
         patch.object(bot, "show_messages", mocks["messages"]), \
         patch.object(bot, "show_send_message_prompt", mocks["send_message"]), \
         patch.object(bot, "handle_register_button", mocks["menu_register"]), \
         patch("appointment.handler.start_appointment_flow", mocks["book_appointment"]):
        for value in callback_values:
            query = SimpleNamespace(
                answer=AsyncMock(),
                data=value,
                message=SimpleNamespace(chat=SimpleNamespace(id=123)),
            )
            update = SimpleNamespace(callback_query=query)
            await bot.handle_callback_query(update, SimpleNamespace(user_data={}))

    for name, mock in mocks.items():
        assert mock.await_count == 1, f"button '{name}' did not route to its handler"


# ── show_messages with a string timestamp (regression for bug #6) ─────────────

@pytest.mark.asyncio
async def test_show_messages_survives_iso_string_timestamp():
    fake_mother = {"_id": "m-1", "name": "Test"}
    fake_msgs = [{
        "sender_name": "Dr. Demo",
        "content": "Please rest",
        "timestamp": "2026-07-16T10:00:00+00:00",  # string, not datetime
    }]
    query = SimpleNamespace(edit_message_text=AsyncMock())

    with patch.object(bot, "db", object()), \
         patch.object(bot.mothers_repo, "get_by_telegram_chat_id", return_value=fake_mother), \
         patch.object(bot.messages_repo, "list_notifications_for_mother", return_value=fake_msgs):
        await bot.show_messages(123, query)

    query.edit_message_text.assert_awaited_once()
    text = query.edit_message_text.await_args.args[0]
    assert "Dr. Demo" in text and "Jul 16, 10:00" in text


# ── /start for a returning mother ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_welcomes_back_registered_mother():
    fake_mother = {"name": "Priya", "assigned_asha_id": "a", "assigned_doctor_id": "d"}
    reply = AsyncMock()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=42),
        effective_user=SimpleNamespace(first_name="Priya", last_name=None, username="p"),
        message=SimpleNamespace(reply_text=reply),
    )

    with patch.object(bot, "db", object()), \
         patch.object(bot.mothers_repo, "get_by_telegram_chat_id", return_value=fake_mother):
        await bot.start(update, SimpleNamespace(user_data={}))

    reply.assert_awaited_once()
    assert "Welcome back" in reply.await_args.args[0]
    assert reply.await_args.kwargs.get("reply_markup") is not None  # menu attached


# ── Document handler (new in this pass) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_document_handler_requires_registration():
    from app.bot import documents

    reply = AsyncMock()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=99),
        message=SimpleNamespace(reply_text=reply, photo=None, document=None),
    )

    with patch.object(documents.mothers_repo, "get_by_telegram_chat_id", return_value=None):
        await documents.handle_document_message(update, SimpleNamespace(bot=None))

    reply.assert_awaited_once()
    assert "/start" in reply.await_args.args[0]
