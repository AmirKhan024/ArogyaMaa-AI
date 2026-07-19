"""
Parallel-graph behavior tests (no network, no DB).

Pins the LangGraph fan-out semantics the app relies on: independent agents
run concurrently, skipped-node parity is preserved, and every fallback path
still produces a scored evaluation.
"""

import json
import time
from unittest.mock import patch

import pytest

from app.ai.graph import create_ArogyaMaa_graph
from app.ai.helpers import build_ai_evaluation


SLEEP_S = 1.0

RISK_JSON = json.dumps({
    "agent": "risk_stratification",
    "risk_level": "MODERATE",
    "confidence": 0.9,
    "risk_score": 45,
    "threshold_violations": [],
    "clinical_flags": ["mild anemia"],
    "referral_urgency": "routine",
    "reasoning": "x" * 120,
})

SYMPTOM_JSON = json.dumps({
    "agent": "symptom_reasoning",
    "symptom_clusters_detected": ["fatigue"],
    "differential_diagnosis": ["anemia"],
    "recommended_questions": ["duration of fatigue?"],
    "urgency_assessment": "routine",
    "reasoning": "y" * 120,
})

TREND_JSON = json.dumps({
    "agent": "trend_analysis",
    "trend_direction": "stable",
    "key_changes": [],
    "monitoring_recommendations": ["continue weekly checks"],
    "reasoning": "z" * 120,
})

NUTRITION_JSON = json.dumps({
    "agent": "nutrition_lifestyle",
    "dietary_recommendations": ["iron-rich food"],
    "lifestyle_modifications": ["light walks"],
    "supplements_needed": ["IFA"],
    "reasoning": "n" * 120,
})

COMMUNICATION_JSON = json.dumps({
    "agent": "communication",
    "message_for_mother": "m" * 60,
    "message_for_asha": "a" * 60,
    "message_for_doctor": "d" * 60,
    "reasoning": "c" * 40,
})


def _dispatch(system_prompt, user_prompt, temp=0.1, sleep=0.0):
    """Return the right canned JSON for whichever agent is calling.

    Each agent's prompt embeds its own JSON template containing a unique
    '"agent": "<name>"' marker - dispatch on that."""
    if sleep:
        time.sleep(sleep)
    text = system_prompt + " " + user_prompt
    if '"agent": "symptom_reasoning"' in text:
        return SYMPTOM_JSON
    if '"agent": "trend_analysis"' in text:
        return TREND_JSON
    if '"agent": "nutrition_lifestyle"' in text:
        return NUTRITION_JSON
    if '"agent": "communication"' in text:
        return COMMUNICATION_JSON
    return RISK_JSON


def _base_state(**overrides):
    state = {
        "assessment_id": "a-1",
        "mother_id": "m-1",
        # glucose + temperature included: the risk node's internal fallback
        # compares them to thresholds and (pre-existing behavior) raises on
        # None, escalating to the outer rule-based fallback instead.
        "vitals": {"bp_systolic": 118, "bp_diastolic": 76, "heart_rate": 82,
                   "hemoglobin": 10.9, "glucose_mg_dl": 95, "temperature": 98.4},
        "symptoms": ["fatigue"],
        "gestational_week": 28,
        "has_uploaded_documents": False,
        "historical_assessments": [],
        "previous_assessments": [
            {"vitals": {"bp_systolic": 115, "bp_diastolic": 74}, "timestamp": "2026-07-01"}
        ],
        "mother_profile": {"name": "Test", "age": 26},
    }
    state.update(overrides)
    return state


def test_independent_agents_run_concurrently():
    """3 LLM agents sleeping 1s each: sequential would be >=4s wall (risk,
    symptom in A; nutrition, communication in B). Parallel: ~2 phases."""
    with patch("app.ai.agents.call_groq_structured",
               side_effect=lambda s, u, temp=0.1: _dispatch(s, u, temp, sleep=SLEEP_S)):
        graph = create_ArogyaMaa_graph()
        t0 = time.perf_counter()
        result = graph.invoke(_base_state())
        wall = time.perf_counter() - t0

    # Phase A: risk || symptom (trend short-circuits, no history in the key
    # it reads). Phase B: nutrition || communication. => ~2 * SLEEP_S.
    assert wall < 2.8 * SLEEP_S, f"graph not parallel: wall={wall:.2f}s"
    # finalize ran (its own state keys are undeclared channels and dropped —
    # same as the pre-migration graph; nothing downstream reads them)
    assert any(t["stage"] == "node:finalize" for t in result["perf_timings"])
    assert result["risk_stratification_result"]["risk_level"] == "MODERATE"
    assert result["symptom_reasoning_result"]["urgency_assessment"] == "routine"
    assert result["nutrition_lifestyle_result"]["dietary_recommendations"]
    assert result["communication_result"]["message_for_mother"]
    assert result["agents_invoked"] == [
        "risk_stratification", "symptom_reasoning", "trend_analysis",
        "nutrition_lifestyle", "communication",
    ]


def test_document_analysis_skipped_without_documents():
    with patch("app.ai.agents.call_groq_structured", side_effect=_dispatch):
        graph = create_ArogyaMaa_graph()
        result = graph.invoke(_base_state(has_uploaded_documents=False))

    # Parity with the old conditional router: key absent, not empty.
    assert "document_analysis_result" not in result
    evaluation = build_ai_evaluation(result)
    assert "document_analysis" not in evaluation.get("agent_outputs", {})


def test_document_analysis_runs_with_documents():
    with patch("app.ai.agents.call_groq_structured", side_effect=_dispatch):
        graph = create_ArogyaMaa_graph()
        result = graph.invoke(_base_state(has_uploaded_documents=True))

    assert "document_analysis_result" in result
    assert "document_analysis" in result["agents_invoked"]


def test_deterministic_short_circuits_make_no_llm_calls():
    """Empty symptoms + no history: symptom and trend nodes must not call the
    LLM (their deterministic branches), leaving only risk/nutrition/comms."""
    calls = []

    def tracking(system_prompt, user_prompt, temp=0.1):
        calls.append(system_prompt[:40])
        return _dispatch(system_prompt, user_prompt, temp)

    with patch("app.ai.agents.call_groq_structured", side_effect=tracking):
        graph = create_ArogyaMaa_graph()
        result = graph.invoke(_base_state(symptoms=[], previous_assessments=[]))

    assert len(calls) == 3, f"expected 3 LLM calls, got {len(calls)}: {calls}"
    # Deterministic short-circuit dicts are present without any LLM call.
    assert result["symptom_reasoning_result"]
    assert result["trend_analysis_result"]


def test_risk_agent_failure_falls_back_to_rule_based():
    """If the risk LLM call explodes, the node's internal fallback (and the
    hybrid rescue in build_ai_evaluation) must still yield a scored result."""

    def failing(system_prompt, user_prompt, temp=0.1):
        text = system_prompt + user_prompt
        if '"agent": "nutrition_lifestyle"' in text:
            return NUTRITION_JSON
        if '"agent": "communication"' in text:
            return COMMUNICATION_JSON
        raise RuntimeError("Groq unavailable")

    with patch("app.ai.agents.call_groq_structured", side_effect=failing):
        graph = create_ArogyaMaa_graph()
        result = graph.invoke(_base_state())

    assert "risk_stratification_result" in result
    evaluation = build_ai_evaluation(result)
    assert evaluation["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert isinstance(evaluation["risk_score"], (int, float))


def test_pipeline_completes_without_groq_key(monkeypatch):
    """CLAUDE.md invariant: killing GROQ access degrades to rule-based
    fallbacks, never a crash."""

    def no_key(*args, **kwargs):
        raise RuntimeError("no api key")

    with patch("app.ai.agents.call_groq_structured", side_effect=no_key):
        graph = create_ArogyaMaa_graph()
        result = graph.invoke(_base_state())

    assert any(t["stage"] == "node:finalize" for t in result["perf_timings"])
    evaluation = build_ai_evaluation(result)
    assert evaluation["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
