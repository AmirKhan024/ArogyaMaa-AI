"""
Simple AI Evaluation Fallback

When langgraph is not available, use rule-based risk scoring.
"""

from datetime import datetime


def calculate_risk_score_fallback(vital_signs, symptoms):
    """
    Calculate risk score based on vitals and symptoms (0-100).
    This is a fallback when AI agent is not available.
    """
    score = 0
    risk_factors = []
    
    # Blood Pressure Scoring (0-40 points)
    # Handle both naming conventions
    bp_systolic = vital_signs.get('blood_pressure_systolic') or vital_signs.get('bp_systolic', 120)
    bp_diastolic = vital_signs.get('blood_pressure_diastolic') or vital_signs.get('bp_diastolic', 80)
    
    if bp_systolic >= 160 or bp_diastolic >= 110:
        score += 40
        risk_factors.append("Severe hypertension (BP >= 160/110)")
    elif bp_systolic >= 140 or bp_diastolic >= 90:
        score += 30
        risk_factors.append("Hypertension (BP >= 140/90)")
    elif bp_systolic >= 130 or bp_diastolic >= 85:
        score += 15
        risk_factors.append("Elevated BP")
    
    # Hemoglobin Scoring (0-20 points)
    hemoglobin = vital_signs.get('hemoglobin', 12)
    if hemoglobin < 7:
        score += 20
        risk_factors.append("Severe anemia (Hb < 7)")
    elif hemoglobin < 9:
        score += 15
        risk_factors.append("Moderate anemia (Hb < 9)")
    elif hemoglobin < 11:
        score += 8
        risk_factors.append("Mild anemia (Hb < 11)")
    
    # Weight/BMI (0-15 points)
    weight = vital_signs.get('weight') or vital_signs.get('weight_kg', 60)
    if weight < 45:
        score += 15
        risk_factors.append("Underweight (< 45kg)")
    elif weight > 90:
        score += 10
        risk_factors.append("Overweight (> 90kg)")
    
    # Glucose (0-15 points)
    glucose = vital_signs.get('blood_glucose_random') or vital_signs.get('glucose_mg_dl', 90)
    if glucose >= 200:
        score += 15
        risk_factors.append("Hyperglycemia (>= 200)")
    elif glucose >= 140:
        score += 10
        risk_factors.append("Elevated glucose (>= 140)")
    elif glucose < 60:
        score += 12
        risk_factors.append("Hypoglycemia (< 60)")
    
    # Symptoms (0-10 points)
    danger_symptoms = ['bleeding', 'severe_headache', 'vision_problems', 'blurred_vision', 'chest_pain', 'seizures']
    warning_symptoms = ['swelling', 'vomiting', 'fever', 'abdominal_pain', 'nausea', 'headache']
    
    danger_count = 0
    for symptom in symptoms:
        if symptom.lower() in danger_symptoms:
            score += 10
            danger_count += 1
            risk_factors.append(f"Danger symptom: {symptom}")
            break  # Only count one danger symptom
    
    if danger_count == 0:
        for symptom in symptoms:
            if symptom.lower() in warning_symptoms:
                score += 5
                risk_factors.append(f"Warning symptom: {symptom}")
                break  # Only count one warning symptom
    
    # Determine risk category
    if score >= 70:
        risk_category = "CRITICAL"
        recommended_actions = ["immediate_hospital_referral", "call_ambulance", "doctor_visit_immediately"]
    elif score >= 50:
        risk_category = "HIGH"
        recommended_actions = ["doctor_visit_24h", "monitor_closely", "daily_bp_checks"]
    elif score >= 30:
        risk_category = "MODERATE"
        recommended_actions = ["doctor_visit_week", "continue_monitoring", "follow_care_plan"]
    else:
        risk_category = "LOW"
        recommended_actions = ["routine_checkup", "healthy_diet", "regular_exercise"]
    
    return {
        "risk_score": min(score, 100),  # Cap at 100
        "risk_category": risk_category,
        "risk_factors": risk_factors,
        "recommended_actions": recommended_actions
    }


def build_fallback_ai_evaluation(assessment, mother, historical):
    """
    Build AI evaluation using fallback rules when langgraph unavailable.
    """
    vital_signs = assessment.get('vital_signs', {})
    symptoms = assessment.get('symptoms', [])
    
    # Calculate risk
    risk_data = calculate_risk_score_fallback(vital_signs, symptoms)
    
    # Build AI evaluation structure
    ai_evaluation = {
        "risk_score": risk_data['risk_score'],
        "risk_category": risk_data['risk_category'],
        "confidence": 0.75,  # Lower confidence for rule-based
        "agent_outputs": {
            "risk_stratification": {
                "risk_level": risk_data['risk_category'],
                "urgency": "high" if risk_data['risk_score'] >= 50 else "medium",
                "thresholds_exceeded": risk_data['risk_factors'],
                "reasoning": f"Risk score {risk_data['risk_score']}/100 based on clinical thresholds. " + 
                            (", ".join(risk_data['risk_factors']) if risk_data['risk_factors'] else "No major risk factors detected.")
            },
            "symptom_reasoning": {
                "clusters_detected": symptoms,
                "severity_assessment": "moderate" if len(symptoms) >= 3 else "mild" if len(symptoms) > 0 else "none",
                "reasoning": f"Reported symptoms: {', '.join(symptoms) if symptoms else 'None reported'}. " +
                            (f"Multiple symptoms ({len(symptoms)}) require attention." if len(symptoms) >= 3 else 
                             f"{len(symptoms)} symptom(s) noted." if len(symptoms) > 0 else "No symptoms reported.")
            },
            "trend_analysis": {
                "trend_direction": "stable" if len(historical) == 0 else "monitoring",
                "worsening_indicators": [],
                "stable_indicators": [],
                "reasoning": f"Assessment #{len(historical) + 1}. Continue monitoring trends."
            },
            "document_analysis": {
                "documents_processed": 0,
                "key_findings": [],
                "reasoning": "No documents uploaded for analysis in this assessment."
            },
            "nutrition_lifestyle": {
                "nutritional_recommendations": [
                    "Iron-rich foods (spinach, lentils, red meat)" if vital_signs.get('hemoglobin', 12) < 11 else "Maintain balanced diet",
                    "Reduce salt intake" if vital_signs.get('blood_pressure_systolic', 120) > 140 else "Normal salt intake",
                    "Frequent small meals to manage glucose" if vital_signs.get('blood_glucose_random', 100) > 140 else "Regular meal timing"
                ],
                "lifestyle_advice": [
                    "Rest and avoid stress" if risk_data['risk_score'] >= 50 else "Regular light exercise",
                    "Monitor blood pressure daily" if vital_signs.get('blood_pressure_systolic', 120) > 140 else "Weekly BP monitoring",
                    "Stay hydrated - 8-10 glasses of water daily"
                ],
                "reasoning": f"Recommendations based on current health status ({risk_data['risk_category']} risk). " +
                            "Focus on nutrition and lifestyle modifications to support maternal health."
            },
            "communication": {
                "mother_message": f"Your health checkup shows {risk_data['risk_category'].lower()} risk level. " +
                                ("Please consult a doctor within 24 hours." if risk_data['risk_score'] >= 50 else 
                                 "Continue your regular checkups and follow your care plan.")
            }
        },
        "recommended_actions": risk_data['recommended_actions'],
        "requires_doctor_review": risk_data['risk_score'] >= 50,
        "evaluated_at": datetime.utcnow(),
        "evaluation_method": "rule_based_fallback"
    }
    
    return ai_evaluation
