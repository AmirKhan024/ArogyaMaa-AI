"""
Agent Node Implementations with Structured Output using Pydantic

Each agent uses:
- Pydantic models for type-safe structured output  
- Proper system/human/AI message formatting
- Groq API with llama-3.3-70b-versatile
- Comprehensive error handling with fallbacks
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from .state import ArogyaMaaState


# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
DEFAULT_MODEL = "llama-3.3-70b-versatile"


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================

class RiskStratificationOutput(BaseModel):
    """Structured output for risk stratification agent - ensures type safety"""
    agent: str = Field(default="risk_stratification")
    risk_level: str = Field(..., description="Risk level: LOW, MODERATE, HIGH, or CRITICAL")
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_score: int = Field(..., ge=0, le=100, description="0-100 numerical risk score")
    threshold_violations: List[str] = Field(default_factory=list)
    clinical_flags: List[str] = Field(default_factory=list)
    referral_urgency: str = Field(...)
    reasoning: str = Field(..., min_length=100)


class SymptomReasoningOutput(BaseModel):
    """Structured output for symptom reasoning agent"""
    agent: str = Field(default="symptom_reasoning")
    symptom_clusters_detected: List[str] = Field(default_factory=list)
    differential_diagnosis: List[str] = Field(default_factory=list)
    recommended_questions: List[str] = Field(default_factory=list)
    urgency_assessment: str = Field(...)
    reasoning: str = Field(..., min_length=100)


class TrendAnalysisOutput(BaseModel):
    """Structured output for trend analysis agent"""
    agent: str = Field(default="trend_analysis")
    trend_direction: str = Field(...)
    key_changes: List[str] = Field(default_factory=list)
    monitoring_recommendations: List[str] = Field(default_factory=list)
    reasoning: str = Field(..., min_length=100)


class NutritionLifestyleOutput(BaseModel):
    """Structured output for nutrition and lifestyle agent"""
    agent: str = Field(default="nutrition_lifestyle")
    dietary_recommendations: List[str] = Field(default_factory=list)
    lifestyle_modifications: List[str] = Field(default_factory=list)
    supplements_needed: List[str] = Field(default_factory=list)
    reasoning: str = Field(..., min_length=100)


class CommunicationOutput(BaseModel):
    """Structured output for communication agent"""
    agent: str = Field(default="communication")
    message_for_mother: str = Field(..., min_length=50)
    message_for_asha: str = Field(..., min_length=50)
    message_for_doctor: str = Field(..., min_length=50)
    reasoning: str = Field(..., min_length=30)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def call_groq_structured(system_msg: str, user_msg: str, temp: float = 0.1) -> str:
    """Call Groq API with proper system/human message formatting"""
    response = groq_client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        temperature=temp,
        max_tokens=4000,
        response_format={"type": "json_object"}  # Force JSON output
    )
    return response.choices[0].message.content


def parse_and_validate(response_text: str, model_class: BaseModel) -> dict:
    """Parse JSON and validate with Pydantic model"""
    data = json.loads(response_text.strip())
    validated = model_class(**data)
    return validated.model_dump()


# ============================================================================
# ORCHESTRATOR AGENT
# ============================================================================

def orchestrator_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """Orchestrator - determines which agents to invoke"""
    print("\n[ORCHESTRATOR] Starting AI analysis pipeline...")
    
    agents_to_invoke = ["risk_stratification", "symptom_reasoning", "trend_analysis"]
    
    if state.get("has_uploaded_documents"):
        agents_to_invoke.append("document_analysis")
    
    agents_to_invoke.extend(["nutrition_lifestyle", "communication"])
    
    state["agents_invoked"] = agents_to_invoke
    state["timestamp"] = datetime.utcnow().isoformat()
    
    print(f"[ORCHESTRATOR] Will invoke: {', '.join(agents_to_invoke)}")
    return state


# ============================================================================
# RISK STRATIFICATION AGENT  
# ============================================================================

def risk_stratification_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """
    Risk Stratification with PROPER SCORING LOGIC
    
    DANGER SYMPTOMS = CRITICAL risk (80-100 points)
    SEVERE VITALS = HIGH risk (60-80 points)
    MODERATE VITALS = MODERATE risk (30-60 points)
    NORMAL = LOW risk (0-30 points)
    """
    print("\n[RISK STRATIFICATION] Analyzing with proper clinical scoring...")
    
    vitals = state.get("vitals", {})
    symptoms = state.get("symptoms", [])
    gestational_week = state.get("gestational_week", 0)
    
    bp_sys = vitals.get('bp_systolic', 0)
    bp_dias = vitals.get('bp_diastolic', 0)
    # Handle both hemoglobin field name formats
    hb = vitals.get('hemoglobin') or vitals.get('hemoglobin_g_dl') or 0
    glucose = vitals.get('blood_glucose_random') or vitals.get('glucose_mg_dl') or 0
    hr = vitals.get('heart_rate', 0)
    temp = vitals.get('temperature', 0)
    # Handle both weight field name formats
    weight = vitals.get('weight') or vitals.get('weight_kg') or 0
    
    symptoms_text = ', '.join(symptoms) if symptoms else "No symptoms"
    
    system_msg = """You are an expert obstetrician with 25+ years experience in high-risk pregnancy management.
You provide evidence-based risk stratification using WHO and Indian maternal health guidelines.
You MUST follow this STRICT SCORING SYSTEM:

**DANGER SYMPTOMS (Each = +40 points, CRITICAL priority):**
- bleeding (antepartum hemorrhage)
- decreased_fetal_movement (fetal distress)
- severe_headache (preeclampsia)
- vision_changes (preeclampsia)
- convulsions (eclampsia)
- severe_abdominal_pain (placental abruption)

**SEVERE VITAL ABNORMALITIES (Each = +30 points):**
- BP ≥160/110 mmHg (severe hypertension)
- Hemoglobin <7 g/dL (severe anemia)
- Temperature >102°F (high fever)
- Glucose >200 mg/dL (severe hyperglycemia)

**MODERATE ABNORMALITIES (Each = +20 points):**
- BP 140-160/90-110 mmHg (hypertension)
- Hemoglobin 7-10 g/dL (moderate anemia)  
- Temperature 100.4-102°F (fever)
- Glucose 140-200 mg/dL (hyperglycemia)

**RISK LEVELS:**
- CRITICAL: 80-100 (immediate emergency)
- HIGH: 60-79 (within 24 hours)
- MODERATE: 30-59 (within week)
- LOW: 0-29 (routine monitoring)

Return ONLY valid JSON matching the exact schema. No other text."""

    user_msg = f"""Analyze maternal health and calculate precise risk score.

**PATIENT DATA (Week {gestational_week}):**

**Vitals:**
- BP: {bp_sys}/{bp_dias} mmHg (Severe: ≥160/110, Moderate: 140-160/90-110)
- Heart Rate: {hr} bpm (Normal: 60-100)
- Hemoglobin: {hb} g/dL (Severe anemia: <7, Moderate: 7-10, Normal: ≥11)
- Glucose: {glucose} mg/dL (Severe: >200, Moderate: 140-200, Normal: <140)
- Temperature: {temp}°F (High fever: >102, Fever: 100.4-102, Normal: 97-99)

**Symptoms:** {symptoms_text}

**SCORING INSTRUCTIONS:**
1. Identify ALL danger symptoms present → Add 40 points EACH
2. Identify ALL severe vital abnormalities → Add 30 points EACH
3. Identify ALL moderate abnormalities → Add 20 points EACH
4. Sum total score (max 100)
5. Assign risk level based on score ranges above
6. Write detailed reasoning (200+ words) explaining:
   - Each vital parameter and threshold status
   - Symptom cluster analysis  
   - Danger signs present
   - Maternal/fetal risks
   - Score calculation breakdown
   - Why this risk level and urgency

Return this EXACT JSON structure:
{{
  "agent": "risk_stratification",
  "risk_level": "CRITICAL",
  "confidence": 0.95,
  "risk_score": 85,
  "threshold_violations": ["BP: 180/90 exceeds severe threshold ≥160/110", "Symptom: bleeding (DANGER)"],
  "clinical_flags": ["Severe hypertension", "Antepartum hemorrhage"],
  "referral_urgency": "immediate",
  "reasoning": "Write 200+ word clinical analysis with SCORE BREAKDOWN showing how you calculated the risk_score"
}}"""

    try:
        print(f"[RISK STRATIFICATION] Calling {DEFAULT_MODEL}...")
        response_text = call_groq_structured(system_msg, user_msg, temp=0.1)
        
        print(f"[RISK STRATIFICATION] Response (first 400 chars): {response_text[:400]}")
        
        result = parse_and_validate(response_text, RiskStratificationOutput)
        state["risk_stratification_result"] = result
        
        print(f"[RISK STRATIFICATION] ✓ Risk: {result['risk_level']} ({result['risk_score']}/100), Urgency: {result['referral_urgency']}")
        
    except Exception as e:
        import traceback
        print(f"[RISK STRATIFICATION] ❌ Error: {e}")
        print(traceback.format_exc())
        
        # ENHANCED FALLBACK with proper scoring
        risk_score = 0
        violations = []
        flags = []
        
        # DANGER SYMPTOMS (+40 each)
        danger_symptoms = ["bleeding", "decreased_fetal_movement", "severe_headache", 
                          "vision_changes", "convulsions", "severe_abdominal_pain"]
        for sym in symptoms:
            if sym in danger_symptoms:
                risk_score += 40
                violations.append(f"DANGER SYMPTOM: {sym.replace('_', ' ')}")
                flags.append(f"⚠️ {sym.replace('_', ' ').upper()}")
        
        # SEVERE VITALS (+30 each)
        if bp_sys >= 160 or bp_dias >= 110:
            risk_score += 30
            violations.append(f"BP {bp_sys}/{bp_dias} mmHg ≥ severe threshold 160/110")
            flags.append("Severe hypertension")
        elif bp_sys >= 140 or bp_dias >= 90:
            risk_score += 20
            violations.append(f"BP {bp_sys}/{bp_dias} mmHg ≥ threshold 140/90")
            flags.append("Hypertension")
        
        if hb > 0 and hb < 7:
            risk_score += 30
            violations.append(f"Hb {hb} g/dL < severe anemia threshold 7")
            flags.append("Severe anemia")
        elif hb > 0 and hb < 10:
            risk_score += 20
            violations.append(f"Hb {hb} g/dL < anemia threshold 10")
            flags.append("Moderate anemia")
        
        if glucose > 200:
            risk_score += 30
            violations.append(f"Glucose {glucose} mg/dL > severe threshold 200")
            flags.append("Severe hyperglycemia")
        elif glucose > 140:
            risk_score += 20
            violations.append(f"Glucose {glucose} mg/dL > threshold 140")
            flags.append("Hyperglycemia")
        
        if temp > 102:
            risk_score += 30
            violations.append(f"Temperature {temp}°F > high fever threshold 102")
            flags.append("High fever")
        elif temp > 100.4:
            risk_score += 20
            violations.append(f"Temperature {temp}°F > fever threshold 100.4")
            flags.append("Fever")
        
        # Cap at 100
        risk_score = min(risk_score, 100)
        
        # Determine risk level
        if risk_score >= 80:
            risk_level = "CRITICAL"
            urgency = "immediate"
        elif risk_score >= 60:
            risk_level = "HIGH"
            urgency = "within_24_hours"
        elif risk_score >= 30:
            risk_level = "MODERATE"
            urgency = "within_week"
        else:
            risk_level = "LOW"
            urgency = "routine"
        
        reasoning = f"FALLBACK RULE-BASED ASSESSMENT at {gestational_week} weeks: "
        reasoning += f"Risk score calculated as {risk_score}/100. "
        reasoning += f"Vitals: BP {bp_sys}/{bp_dias} mmHg, Hb {hb} g/dL, Glucose {glucose} mg/dL, Temp {temp}°F. "
        reasoning += f"Symptoms: {symptoms_text}. "
        reasoning += f"Detected {len(violations)} threshold violations. "
        reasoning += f"Clinical significance: {' '.join(flags)}. "
        reasoning += f"Risk level {risk_level} requires {urgency} medical attention."
        
        state["risk_stratification_result"] = {
            "agent": "risk_stratification",
            "risk_level": risk_level,
            "confidence": 0.75,
            "risk_score": risk_score,
            "threshold_violations": violations,
            "clinical_flags": flags,
            "referral_urgency": urgency,
            "reasoning": reasoning
        }
    
    return state


# ============================================================================
# SYMPTOM REASONING AGENT
# ============================================================================

def symptom_reasoning_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """Symptom pattern recognition and cluster analysis"""
    print("\n[SYMPTOM REASONING] Analyzing symptom patterns...")
    
    symptoms = state.get("symptoms", [])
    gestational_week = state.get("gestational_week", 0)
    vitals = state.get("vitals", {})
    
    if not symptoms:
        state["symptom_reasoning_result"] = {
            "agent": "symptom_reasoning",
            "symptom_clusters_detected": [],
            "differential_diagnosis": [],
            "recommended_questions": ["Have you noticed any changes in fetal movement?", "Any swelling in hands/face?", "Any headaches or visual disturbances?"],
            "urgency_assessment": "routine_monitoring",
            "reasoning": f"No symptoms reported at {gestational_week} weeks gestation. This is reassuring, indicating no acute maternal/fetal distress. However, asymptomatic conditions (gestational diabetes, chronic hypertension, IUGR) cannot be ruled out. Patient should continue routine antenatal care, monitor daily fetal movements (kick counts), and be educated on warning signs requiring immediate attention: vaginal bleeding, severe headache, vision changes, decreased fetal movement, fluid leakage. Regular screening for GDM and preeclampsia should continue per protocol."
        }
        return state
    
    symptoms_text = ', '.join(symptoms)
    
    system_msg = """You are an expert obstetrician specializing in symptom pattern recognition.
You identify dangerous symptom clusters:
- Preeclampsia triad: headache + edema + vision changes + high BP
- Preterm labor: contractions + back pain + pelvic pressure
- Placental abruption: bleeding + severe abdominal pain + uterine tenderness
- Infection: fever + abdominal pain + discharge

Return ONLY valid JSON. Be specific and clinical."""

    user_msg = f"""Analyze symptom presentation in pregnancy.

**DATA:**
- Week: {gestational_week}
- Symptoms: {symptoms_text}
- BP: {vitals.get('bp_systolic', 0)}/{vitals.get('bp_diastolic', 0)} mmHg

**TASK:**
1. Identify symptom clusters (preeclampsia, preterm labor, infection, hemorrhage)
2. Generate differential diagnosis ranked by likelihood
3. Recommend follow-up questions
4. Assess urgency
5. Write 150+ word reasoning covering clusters, significance, red flags, diagnoses

Return JSON:
{{
  "agent": "symptom_reasoning",
  "symptom_clusters_detected": ["Preeclampsia triad: headache+edema+hypertension"],
  "differential_diagnosis": ["Preeclampsia with severe features", "Gestational hypertension"],
  "recommended_questions": ["Right upper quadrant pain?", "Seeing spots/flashing lights?"],
  "urgency_assessment": "immediate",
  "reasoning": "150+ word analysis of symptoms, clusters, diagnoses, urgency"
}}"""

    try:
        response_text = call_groq_structured(system_msg, user_msg, temp=0.2)
        result = parse_and_validate(response_text, SymptomReasoningOutput)
        state["symptom_reasoning_result"] = result
        print(f"[SYMPTOM REASONING] ✓ Clusters: {len(result['symptom_clusters_detected'])}, Urgency: {result['urgency_assessment']}")
    except Exception as e:
        print(f"[SYMPTOM REASONING] ❌ {e}")
        state["symptom_reasoning_result"] = {
            "agent": "symptom_reasoning",
            "symptom_clusters_detected": [f"Multiple symptoms: {symptoms_text}"],
            "differential_diagnosis": ["Requires clinical evaluation"],
            "recommended_questions": ["Describe each symptom in detail", "When did symptoms start?", "Are symptoms worsening?"],
            "urgency_assessment": "within_24_hours",
            "reasoning": f"Patient reports {len(symptoms)} symptoms ({symptoms_text}) at {gestational_week} weeks. Multiple symptoms warrant comprehensive clinical evaluation to rule out serious conditions (preeclampsia, preterm labor, infection, hemorrhage). Recommend detailed symptom history, physical examination, appropriate investigations (CBC, LFT, urine protein, NST if indicated). Monitor closely for development of danger signs."
        }
    
    return state


# ============================================================================
# TREND ANALYSIS AGENT
# ============================================================================

def trend_analysis_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """Longitudinal trend analysis"""
    print("\n[TREND ANALYSIS] Analyzing health trends...")
    
    previous_assessments = state.get("previous_assessments", [])
    current_vitals = state.get("vitals", {})
    gestational_week = state.get("gestational_week", 0)
    
    if not previous_assessments:
        state["trend_analysis_result"] = {
            "agent": "trend_analysis",
            "trend_direction": "baseline",
            "key_changes": [],
            "monitoring_recommendations": ["Establish baseline vitals", "Monitor BP weekly", "Track weight gain", "Monitor fetal movement daily"],
            "reasoning": f"First assessment at {gestational_week} weeks - establishing baseline. Current vitals: BP {current_vitals.get('bp_systolic', 0)}/{current_vitals.get('bp_diastolic', 0)} mmHg, Hb {current_vitals.get('hemoglobin') or current_vitals.get('hemoglobin_g_dl') or 0} g/dL, Weight {current_vitals.get('weight') or current_vitals.get('weight_kg') or 0} kg. These baseline values will track trends in future visits. Monitor for: (1) BP trends for gestational hypertension/preeclampsia, (2) Weight gain trajectory for nutrition/edema, (3) Hemoglobin for anemia, (4) New symptom development. Return for regular antenatal care and report concerning symptoms immediately."
        }
        return state
    
    prev_data = []
    for i, assessment in enumerate(previous_assessments[-3:], 1):
        v = assessment.get("vitals", {})
        # Handle both field name formats
        hb = v.get('hemoglobin') or v.get('hemoglobin_g_dl') or 0
        wt = v.get('weight') or v.get('weight_kg') or 0
        prev_data.append(f"Visit {i}: BP {v.get('bp_systolic', 0)}/{v.get('bp_diastolic', 0)}, Hb {hb}, Wt {wt} kg")
    
    prev_text = "\n".join(prev_data)
    # Handle both field name formats for current vitals
    current_hb = current_vitals.get('hemoglobin') or current_vitals.get('hemoglobin_g_dl') or 0
    current_wt = current_vitals.get('weight') or current_vitals.get('weight_kg') or 0
    current_text = f"Current: BP {current_vitals.get('bp_systolic', 0)}/{current_vitals.get('bp_diastolic', 0)}, Hb {current_hb}, Wt {current_wt} kg"
    
    system_msg = """You are an expert in longitudinal maternal health monitoring.
You identify concerning trends: worsening hypertension, declining hemoglobin, excessive weight gain.
Return ONLY valid JSON."""

    user_msg = f"""Analyze maternal health trends.

**TREND DATA (Week {gestational_week}):**

Previous:
{prev_text}

{current_text}

**TASK:**
1. Trend direction: improving/stable/worsening
2. Key changes from previous visits
3. Monitoring recommendations
4. Write 150+ word reasoning on BP, Hb, weight trends and clinical significance

Return JSON:
{{
  "agent": "trend_analysis",
  "trend_direction": "worsening",
  "key_changes": ["BP increased from 120/80 to 145/90 over 2 weeks"],
  "monitoring_recommendations": ["Monitor BP twice weekly", "Repeat Hb in 1 week"],
  "reasoning": "150+ word trend analysis"
}}"""

    try:
        response_text = call_groq_structured(system_msg, user_msg, temp=0.2)
        result = parse_and_validate(response_text, TrendAnalysisOutput)
        state["trend_analysis_result"] = result
        print(f"[TREND ANALYSIS] ✓ Direction: {result['trend_direction']}, Changes: {len(result['key_changes'])}")
    except Exception as e:
        print(f"[TREND ANALYSIS] ❌ {e}")
        state["trend_analysis_result"] = {
            "agent": "trend_analysis",
            "trend_direction": "stable",
            "key_changes": ["Monitoring ongoing"],
            "monitoring_recommendations": ["Continue routine antenatal care", "Monitor vitals weekly"],
            "reasoning": f"Comparing current assessment at {gestational_week} weeks with {len(previous_assessments)} previous assessments. Trend analysis tracks changes in blood pressure (detect gestational hypertension), hemoglobin (anemia progression), weight gain (nutrition/edema). Continue monitoring maternal health parameters. Regular ANC visits recommended."
        }
    
    return state


# ============================================================================
# NUTRITION & LIFESTYLE AGENT
# ============================================================================

def nutrition_lifestyle_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """Personalized nutrition and lifestyle recommendations"""
    print("\n[NUTRITION & LIFESTYLE] Generating recommendations...")
    
    vitals = state.get("vitals", {})
    gestational_week = state.get("gestational_week", 0)
    risk_result = state.get("risk_stratification_result", {})
    
    # Handle both field name formats
    hb = vitals.get('hemoglobin') or vitals.get('hemoglobin_g_dl') or 0
    glucose = vitals.get('blood_glucose_random') or vitals.get('glucose_mg_dl') or 0
    risk_level = risk_result.get('risk_level', 'UNKNOWN')
    
    system_msg = """You are a maternal nutrition specialist expert in Indian dietary patterns.
Provide evidence-based, culturally appropriate nutrition advice for pregnant women.
Return ONLY valid JSON."""

    user_msg = f"""Generate nutrition recommendations.

**DATA:**
- Week: {gestational_week}
- Hb: {hb} g/dL (Normal: ≥11)
- Glucose: {glucose} mg/dL (Normal: <140)
- Risk: {risk_level}

**TASK:**
1. Dietary advice (iron-rich foods, glucose management, protein)
2. Lifestyle modifications (activity, rest, stress)
3. Supplements needed
4. Write 150+ word reasoning explaining recommendations based on current health status

Return JSON:
{{
  "agent": "nutrition_lifestyle",
  "dietary_recommendations": ["Iron-rich: spinach, lentils, jaggery", "Protein in every meal", "Limit sugary foods"],
  "lifestyle_modifications": ["30 min gentle walking daily", "8 hours sleep", "Avoid heavy lifting"],
  "supplements_needed": ["Iron 100mg daily with vitamin C", "Folic acid 400mcg", "Calcium 1000mg"],
  "reasoning": "150+ word nutritional analysis"
}}"""

    try:
        response_text = call_groq_structured(system_msg, user_msg, temp=0.3)
        result = parse_and_validate(response_text, NutritionLifestyleOutput)
        state["nutrition_lifestyle_result"] = result
        print(f"[NUTRITION & LIFESTYLE] ✓ {len(result['dietary_recommendations'])} dietary, {len(result['lifestyle_modifications'])} lifestyle recs")
    except Exception as e:
        print(f"[NUTRITION & LIFESTYLE] ❌ {e}")
        state["nutrition_lifestyle_result"] = {
            "agent": "nutrition_lifestyle",
            "dietary_recommendations": ["Balanced diet with fruits, vegetables, whole grains", "Iron-rich foods: spinach, beans, jaggery", "Adequate protein: dal, eggs, milk", "Hydration: 8-10 glasses water daily"],
            "lifestyle_modifications": ["Regular gentle exercise like walking", "8 hours sleep nightly", "Avoid stress and heavy lifting"],
            "supplements_needed": ["Iron and folic acid as prescribed", "Calcium supplements"],
            "reasoning": f"Standard prenatal nutrition at {gestational_week} weeks. Hemoglobin {hb} g/dL requires iron-rich diet and supplementation if low. Balanced nutrition supports fetal growth and maternal health. Regular activity maintains fitness for labor. Adequate rest supports pregnancy demands. Follow healthcare provider's supplement recommendations."
        }
    
    return state


# ============================================================================
# COMMUNICATION AGENT
# ============================================================================

def communication_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """Generate tailored messages for different stakeholders"""
    print("\n[COMMUNICATION] Generating stakeholder messages...")
    
    risk_result = state.get("risk_stratification_result", {})
    risk_level = risk_result.get("risk_level", "UNKNOWN")
    risk_score = risk_result.get("risk_score", 0)
    urgency = risk_result.get("referral_urgency", "routine")
    gestational_week = state.get("gestational_week", 0)
    
    system_msg = """You are a health communication specialist in maternal health education.
Create clear, empathetic messages for mother (simple), ASHA (clinical), doctor (technical).
Return ONLY valid JSON."""

    user_msg = f"""Generate communication messages.

**SUMMARY:**
- Week: {gestational_week}
- Risk: {risk_level} ({risk_score}/100)
- Urgency: {urgency}
- Findings: {risk_result.get('reasoning', '')[:200]}

**TASK:**
Create 3 messages:
1. Mother: Simple, reassuring, non-medical language (100+ words)
2. ASHA: Clinical summary with action items (100+ words)
3. Doctor: Technical medical summary (100+ words)

Return JSON:
{{
  "agent": "communication",
  "message_for_mother": "Simple explanation of findings and next steps",
  "message_for_asha": "Clinical summary with action items",
  "message_for_doctor": "Technical medical summary",
  "reasoning": "Communication strategy"
}}"""

    try:
        response_text = call_groq_structured(system_msg, user_msg, temp=0.4)
        result = parse_and_validate(response_text, CommunicationOutput)
        state["communication_result"] = result
        print(f"[COMMUNICATION] ✓ Messages generated for all stakeholders")
    except Exception as e:
        print(f"[COMMUNICATION] ❌ {e}")
        
        if risk_level in ["HIGH", "CRITICAL"]:
            mother_msg = f"Your health checkup at {gestational_week} weeks shows some concerns that need doctor's attention soon. Your risk level is {risk_level} with a score of {risk_score}/100. Please follow the care plan given by your health worker and contact your doctor immediately if you feel unwell. This is important for your baby's health."
            asha_msg = f"URGENT: Mother at {gestational_week} weeks has {risk_level} risk (Score: {risk_score}/100). Ensure doctor consultation {urgency}. Monitor closely for warning signs. Clinical flags: {', '.join(risk_result.get('clinical_flags', [])[:3])}. Immediate follow-up required."
            doctor_msg = f"Patient at {gestational_week} weeks gestation with {risk_level} risk stratification (Score: {risk_score}/100). Urgency: {urgency}. Threshold violations: {len(risk_result.get('threshold_violations', []))}. Review full clinical data and assessment results in portal for detailed findings. Consider immediate evaluation."
        else:
            mother_msg = f"Your health checkup at {gestational_week} weeks looks good with {risk_level} risk level (Score: {risk_score}/100). Continue eating healthy food, taking your medicines, and attending regular checkups. Contact your health worker if you have any concerns between visits."
            asha_msg = f"Mother at {gestational_week} weeks has {risk_level} risk assessment (Score: {risk_score}/100). Continue standard antenatal care. Next visit as scheduled. Monitor for any new symptoms or concerns."
            doctor_msg = f"Patient at {gestational_week} weeks gestation with {risk_level} risk (Score: {risk_score}/100). Routine antenatal care indicated. Review comprehensive assessment details in portal."
        
        state["communication_result"] = {
            "agent": "communication",
            "message_for_mother": mother_msg,
            "message_for_asha": asha_msg,
            "message_for_doctor": doctor_msg,
            "reasoning": f"Fallback communication based on {risk_level} risk and {urgency} urgency."
        }
    
    return state


# ============================================================================
# DOCUMENT ANALYSIS AGENT (Placeholder)
# ============================================================================

def document_analysis_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """Document analysis agent - placeholder for future implementation"""
    print("\n[DOCUMENT ANALYSIS] Processing documents...")
    
    state["document_analysis_result"] = {
        "agent": "document_analysis",
        "documents_processed": 0,
        "key_findings": [],
        "reasoning": "Document analysis feature coming soon"
    }
    
    return state


# ============================================================================
# FINALIZE NODE
# ============================================================================

def finalize_node(state: ArogyaMaaState) -> ArogyaMaaState:
    """
    Finalize Node - Aggregates all agent results and prepares final output.
    
    This is the last node in the workflow that combines all agent outputs
    into a coherent assessment result.
    """
    print("\n[FINALIZE] Aggregating all agent results...")
    
    # Collect all agent results
    results = {
        "risk_stratification": state.get("risk_stratification_result", {}),
        "symptom_reasoning": state.get("symptom_reasoning_result", {}),
        "trend_analysis": state.get("trend_analysis_result", {}),
        "nutrition_lifestyle": state.get("nutrition_lifestyle_result", {}),
        "communication": state.get("communication_result", {}),
        "document_analysis": state.get("document_analysis_result", {})
    }
    
    # Store aggregated results
    state["final_results"] = results
    state["workflow_complete"] = True
    state["completed_at"] = datetime.utcnow().isoformat()
    
    # Extract key information for easy access
    risk_result = results.get("risk_stratification", {})
    state["final_risk_level"] = risk_result.get("risk_level", "UNKNOWN")
    state["final_risk_score"] = risk_result.get("risk_score", 0)
    state["final_confidence"] = risk_result.get("confidence", 0.0)
    
    print(f"[FINALIZE] ✓ Workflow complete: Risk={state['final_risk_level']} ({state['final_risk_score']}/100)")
    
    return state


