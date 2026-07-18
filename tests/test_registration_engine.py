"""
Registration engine unit tests — deterministic paths only (LLM is mocked).

Covers the round-2 regressions: yes/no normalization, EDD/LMP/week derivation,
step skipping, idempotency (re-processing an answer can't double-advance), and
the summary/consent/correction loop.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.ai.registration.engine import RegistrationEngine, _norm_yes_no
from app.ai.registration.questions import REGISTRATION_STEPS


@pytest.fixture()
def engine():
    ai = MagicMock()
    ai._call_groq.return_value = "{}"  # LLM never used in these tests
    return RegistrationEngine(ai)


def _apply(session, updates):
    for k, v in updates.items():
        if v is None:
            session.pop(k, None)
        else:
            session[k] = v


# ── Yes/No normalization ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Yes", "Yes"), ("yes", "Yes"), ("haan", "Yes"), ("हाँ", "Yes"), ("ji", "Yes"),
    ("No", "No"), ("nahi", "No"), ("नहीं", "No"), ("none", "No"), ("Nope", "No"),
    ("maybe", None), ("kal batati hu", None),
])
def test_norm_yes_no(raw, expected):
    assert _norm_yes_no(raw) == expected


# ── Derivations ────────────────────────────────────────────────────────────────

def test_derive_edd_and_week_from_lmp(engine):
    data, updates = {"lmp_date": "2026-05-09"}, {}
    engine._derive(data, updates)
    lmp = date(2026, 5, 9)
    assert data["edd_date"] == (lmp + timedelta(days=280)).isoformat()
    assert int(data["gestational_week"]) == (date.today() - lmp).days // 7


def test_derive_lmp_from_week_and_hallucinated_edd_is_overridden(engine):
    # The model claims a wildly wrong EDD alongside a stated week — LMP wins.
    data, updates = {"gestational_week": "10", "edd_date": "2027-12-06"}, {}
    engine._derive(data, updates)
    lmp = date.today() - timedelta(weeks=10)
    assert data["lmp_date"] == lmp.isoformat()
    assert data["edd_date"] == (lmp + timedelta(days=280)).isoformat()


def test_derive_age_from_dob(engine):
    data, updates = {"dob": "21 April 2005"}, {}
    engine._derive(data, updates)
    assert isinstance(data.get("age"), int) and 18 <= data["age"] <= 30


def test_first_pregnancy_skips_previous_details(engine):
    data, updates = {"first_pregnancy": "Yes"}, {}
    engine._derive(data, updates)
    assert data["previous_pregnancies_count"] == "0"
    assert data["previous_complications"] == "No"
    applicable_ids = [s["id"] for s in engine._applicable(data)]
    assert "previous_details" not in applicable_ids


def test_fetal_movement_skipped_before_week_18(engine):
    ids_early = [s["id"] for s in engine._applicable({"gestational_week": "10"})]
    ids_late = [s["id"] for s in engine._applicable({"gestational_week": "24"})]
    assert "fetal_movement" not in ids_early
    assert "fetal_movement" in ids_late


# ── Flow control ───────────────────────────────────────────────────────────────

def test_keyboard_tap_answers_without_llm(engine):
    session = {}
    updates, text, comp, ui = engine.provide_next_question(session, None)
    assert ui["type"] == "binary"  # language question
    updates, text, comp, ui = engine.provide_next_question(session, "English")
    assert updates["preferred_language"] == "English"
    engine.ai._call_groq.assert_not_called()


def test_reprocessing_same_answer_is_idempotent(engine):
    session = {"preferred_language": "English"}
    u1, t1, _, _ = engine.provide_next_question(session, "9820846046")
    _apply(session, u1)
    # The same answer re-delivered: phone is already set, flow must stay on the
    # SAME next step (about_you) and not skip ahead.
    u2, t2, _, ui2 = engine.provide_next_question(dict(session), "9820846046")
    pending_after = [s["id"] for s in engine._pending({**session, **{k: v for k, v in u2.items() if v}})]
    assert pending_after[0] == "about_you"


def test_progress_prefix_and_speech_text(engine):
    session = {"preferred_language": "English"}
    _, text, _, ui = engine.provide_next_question(session, None)
    assert text.startswith("🌸 Step ")
    assert "Step" not in ui["speech_text"] or "🌸" not in ui["speech_text"]


def test_consent_no_enters_correction_mode(engine):
    # Build a nearly-complete session.
    session = {s["fields"][0]["key"]: "x" for s in REGISTRATION_STEPS}
    for step in REGISTRATION_STEPS:
        for f in step["fields"]:
            session[f["key"]] = "Yes" if f["type"] == "yes_no" else "1"
    session["preferred_language"] = "English"
    session["first_pregnancy"] = "Yes"
    session["gestational_week"] = "20"
    session.pop("doctor_consent")

    updates, text, comp, _ = engine.provide_next_question(session, "✏️ Something is wrong")
    assert not comp
    assert updates.get("_correction_mode") is True
    assert "fix" in text.lower() or "ठीक" in text


def test_completion_message_has_next_steps(engine):
    session = {}
    for step in REGISTRATION_STEPS:
        for f in step["fields"]:
            session[f["key"]] = "Yes" if f["type"] == "yes_no" else "value"
    session["preferred_language"] = "English"
    session["full_name"] = "Sunita"
    session["gestational_week"] = "22"
    _, text, comp, _ = engine.provide_next_question(session, None)
    assert comp
    assert "Sunita" in text and "ASHA" in text
