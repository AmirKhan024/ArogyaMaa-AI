"""Deterministic tests for the rule-based fallback risk scorer."""

from app.ai.fallback import calculate_risk_score_fallback


def test_normal_vitals_low_risk():
    result = calculate_risk_score_fallback(
        {"bp_systolic": 118, "bp_diastolic": 76, "hemoglobin": 12, "weight_kg": 60, "glucose_mg_dl": 90},
        [],
    )
    assert result["risk_category"] == "LOW"
    assert result["risk_score"] < 30


def test_severe_hypertension_and_anemia_high_risk():
    result = calculate_risk_score_fallback(
        {"bp_systolic": 170, "bp_diastolic": 115, "hemoglobin": 6.5},
        [],
    )
    # BP >=160/110 (+40) and Hb <7 (+20) -> >= 50
    assert result["risk_score"] >= 50
    assert result["risk_category"] in ("HIGH", "CRITICAL")


def test_danger_symptom_flagged():
    result = calculate_risk_score_fallback(
        {"bp_systolic": 120, "bp_diastolic": 80, "hemoglobin": 12},
        ["bleeding"],
    )
    assert any("Danger symptom" in f for f in result["risk_factors"])


def test_score_capped_at_100():
    result = calculate_risk_score_fallback(
        {"bp_systolic": 200, "bp_diastolic": 130, "hemoglobin": 5, "weight_kg": 40, "glucose_mg_dl": 260},
        ["seizures"],
    )
    assert result["risk_score"] <= 100
    assert result["risk_category"] == "CRITICAL"
