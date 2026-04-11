"""
AI Evaluation Helpers

Functions to transform LangGraph output into MongoDB ai_evaluation schema.
"""

from datetime import datetime
from typing import Dict, Optional


def build_ai_evaluation(langgraph_result: Dict, langsmith_trace_id: Optional[str] = None) -> Dict:
    """
    Transform LangGraph orchestration output into ai_evaluation schema for MongoDB.
    
    Args:
        langgraph_result: Output from graph.invoke()
        langsmith_trace_id: Optional LangSmith trace ID for observability
    
    Returns:
        Dictionary matching ai_evaluation schema:
        {
            "risk_score": int (0-100),
            "risk_category": str ("LOW", "MODERATE", "HIGH", "CRITICAL"),
            "confidence": float (0.0-1.0),
            "agent_outputs": {
                "risk_stratification": {...},
                "symptom_reasoning": {...},
                "trend_analysis": {...},
                ...
            },
            "recommended_actions": [...],
            "requires_doctor_review": bool,
            "evaluated_at": datetime (UTC),
            "langsmith_trace_id": str (optional)
        }
    """
    # Debug: Print all keys in langgraph_result
    print(f"[HELPER] LangGraph result keys: {list(langgraph_result.keys())}")
    
    # Extract risk stratification result to get risk level and score
    risk_strat = langgraph_result.get("risk_stratification_result", {})
    risk_level = risk_strat.get("risk_level", "MODERATE")
    risk_score = risk_strat.get("risk_score", 50)  # NEW: Use actual AI-calculated score!
    confidence = risk_strat.get("confidence", 0.75)
    
    # Extract agent outputs
    agent_outputs = {}
    
    # Risk Stratification
    if "risk_stratification_result" in langgraph_result:
        # Handle both dict and list threshold violations
        violations = risk_strat.get("threshold_violations", [])
        if violations and isinstance(violations[0], dict):
            # Old format: list of dicts
            thresholds = [v.get("parameter", str(v)) for v in violations]
        else:
            # New format: list of strings
            thresholds = violations
        
        agent_outputs["risk_stratification"] = {
            "risk_level": risk_level,
            "risk_score": risk_score,  # NEW: Include numerical score
            "urgency": risk_strat.get("referral_urgency"),
            "thresholds_exceeded": thresholds,
            "clinical_flags": risk_strat.get("clinical_flags", []),  # NEW: Add flags
            "reasoning": risk_strat.get("reasoning", "No reasoning provided")
        }
        print(f"[HELPER] Risk stratification: {risk_level} ({risk_score}/100)")
    
    # Symptom Reasoning
    if "symptom_reasoning_result" in langgraph_result:
        symp_reason = langgraph_result["symptom_reasoning_result"]
        # Handle both old and new field names
        clusters = symp_reason.get("symptom_clusters_detected", symp_reason.get("symptom_clusters", []))
        
        agent_outputs["symptom_reasoning"] = {
            "clusters_detected": clusters,
            "differential_diagnosis": symp_reason.get("differential_diagnosis", []),  # NEW
            "urgency_assessment": symp_reason.get("urgency_assessment", "unknown"),  # NEW
            "severity_assessment": symp_reason.get("combined_severity", "unknown"),
            "reasoning": symp_reason.get("reasoning", "No reasoning provided")
        }
        print(f"[HELPER] Symptom reasoning: {len(clusters)} clusters detected")
    
    # Trend Analysis
    if "trend_analysis_result" in langgraph_result:
        trend = langgraph_result["trend_analysis_result"]
        agent_outputs["trend_analysis"] = {
            "trend_direction": trend.get("trend_direction", trend.get("overall_trend", "stable")),
            "key_changes": trend.get("key_changes", []),  # NEW field
            "monitoring_recommendations": trend.get("monitoring_recommendations", []),  # NEW
            "worsening_indicators": trend.get("worsening_indicators", []),
            "stable_indicators": trend.get("stable_indicators", []),
            "reasoning": trend.get("reasoning", "No reasoning provided")
        }
        print(f"[HELPER] Trend analysis: {agent_outputs['trend_analysis']['trend_direction']}")
    
    # Document Analysis
    if "document_analysis_result" in langgraph_result:
        doc = langgraph_result["document_analysis_result"]
        agent_outputs["document_analysis"] = {
            "documents_processed": doc.get("documents_processed", 0),
            "key_findings": doc.get("key_findings", []),
            "summary": doc.get("reasoning", "No documents uploaded for analysis"),
            "reasoning": doc.get("reasoning", "No documents uploaded for analysis")
        }
        print(f"[HELPER] Document analysis: {doc.get('documents_processed', 0)} docs processed")
    
    # Nutrition & Lifestyle
    if "nutrition_lifestyle_result" in langgraph_result:
        nutrition = langgraph_result["nutrition_lifestyle_result"]
        agent_outputs["nutrition_lifestyle"] = {
            "dietary_recommendations": nutrition.get("dietary_recommendations", []),  # NEW field name
            "lifestyle_modifications": nutrition.get("lifestyle_modifications", []),  # NEW
            "supplements_needed": nutrition.get("supplements_needed", []),  # NEW
            "nutritional_recommendations": nutrition.get("dietary_recommendations", []),  # For backwards compat
            "lifestyle_advice": nutrition.get("lifestyle_modifications", []),  # For backwards compat
            "recommendations": nutrition.get("dietary_recommendations", []),  # For JS compatibility
            "reasoning": nutrition.get("reasoning", "No reasoning provided")
        }
        print(f"[HELPER] Nutrition: {len(nutrition.get('dietary_recommendations', []))} dietary recs")
    
    # Communication
    if "communication_result" in langgraph_result:
        comm = langgraph_result["communication_result"]
        agent_outputs["communication"] = {
            "message_for_mother": comm.get("message_for_mother", ""),  # NEW field name
            "message_for_asha": comm.get("message_for_asha", ""),  # NEW
            "message_for_doctor": comm.get("message_for_doctor", ""),  # NEW
            "mother_message": comm.get("message_for_mother", ""),  # For backwards compat
            "asha_message": comm.get("message_for_asha", ""),
            "doctor_message": comm.get("message_for_doctor", "")
        }
        print(f"[HELPER] Communication messages generated for all stakeholders")
    
    # Build ai_evaluation object
    ai_evaluation = {
        "risk_score": risk_score,  # Use actual AI-calculated score (0-100)
        "risk_category": risk_level,  # Use actual AI risk level
        "confidence": confidence,  # Use actual AI confidence
        "agent_outputs": agent_outputs,
        "recommended_actions": [],  # Will be populated from agents
        "requires_doctor_review": risk_level in ["HIGH", "CRITICAL"],  # Auto-flag urgent cases
        "evaluated_at": datetime.utcnow()
    }
    
    # Extract recommended actions from various agents
    recommended_actions = []
    
    # From nutrition agent
    if "nutrition_lifestyle_result" in langgraph_result:
        nutrition = langgraph_result["nutrition_lifestyle_result"]
        for rec in nutrition.get("dietary_recommendations", [])[:3]:
            recommended_actions.append(rec)
        for rec in nutrition.get("lifestyle_modifications", [])[:2]:
            recommended_actions.append(rec)
    
    # From symptom reasoning
    if "symptom_reasoning_result" in langgraph_result:
        symp = langgraph_result["symptom_reasoning_result"]
        if symp.get("urgency_assessment") in ["immediate", "urgent"]:
            recommended_actions.insert(0, "⚠️ SEEK IMMEDIATE MEDICAL ATTENTION")
    
    # From risk stratification
    if risk_level in ["HIGH", "CRITICAL"]:
        urgency = risk_strat.get("referral_urgency", "within_24_hours")
        if urgency == "immediate":
            recommended_actions.insert(0, "🚨 EMERGENCY: Contact doctor immediately")
        elif urgency == "within_24_hours":
            recommended_actions.insert(0, "⚠️ HIGH PRIORITY: See doctor within 24 hours")
    
    ai_evaluation["recommended_actions"] = recommended_actions[:5]  # Top 5 actions
    
    # Add LangSmith trace ID if available
    if langsmith_trace_id:
        ai_evaluation["langsmith_trace_id"] = langsmith_trace_id
    
    # Add agents invoked metadata
    if "agents_invoked" in langgraph_result:
        ai_evaluation["agents_invoked"] = langgraph_result["agents_invoked"]
    
    # Add orchestration metadata
    if "orchestration_id" in langgraph_result:
        ai_evaluation["orchestration_id"] = langgraph_result["orchestration_id"]
    
    if "timestamp" in langgraph_result:
        ai_evaluation["orchestration_timestamp"] = langgraph_result["timestamp"]
    
    return ai_evaluation


def prepare_assessment_for_ai(assessment_data: Dict, mother_data: Dict, historical_assessments: list) -> Dict:
    """
    Prepare assessment data in the format expected by LangGraph.
    
    Args:
        assessment_data: Raw assessment from request
        mother_data: Mother profile from MongoDB
        historical_assessments: Previous assessments for this mother
    
    Returns:
        Dictionary matching ArogyaMaaState schema
    """
    pregnancy = mother_data.get('current_pregnancy', {})
    
    # Build LangGraph input state
    ai_input = {
        "assessment_id": str(assessment_data.get('_id', '')),
        "mother_id": str(mother_data.get('_id', '')),
        "assessment_type": "routine",  # Default to routine
        "vitals": assessment_data.get('vitals', {}),
        "symptoms": assessment_data.get('symptoms', []),
        "risk_factors": mother_data.get('risk_factors', []),
        "gestational_week": assessment_data.get('gestational_age_at_assessment', 
                                               pregnancy.get('gestational_age_weeks', 0)),
        "has_lab_results": False,  # TODO: Detect from vitals (hemoglobin, glucose)
        "has_uploaded_documents": len(assessment_data.get('documents_uploaded', [])) > 0,
        "historical_assessments": [],
        "mother_profile": {
            "name": mother_data.get('name', ''),
            "age": mother_data.get('age', 0),
            "preferred_language": mother_data.get('preferred_language', 'hindi'),
            "education_level": mother_data.get('education_level', 'primary'),
            "dietary_restrictions": mother_data.get('dietary_restrictions', []),
            "region": mother_data.get('address', {}).get('village', 'rural_india')
        }
    }
    
    # Add historical assessments if available
    if historical_assessments:
        ai_input["historical_assessments"] = [
            {
                "date": h.get('timestamp').isoformat() if h.get('timestamp') else '',
                "vitals": h.get('vitals', {})
            }
            for h in historical_assessments[:10]  # Last 10 assessments
        ]
    
    # Detect emergency based on vitals
    vitals = ai_input["vitals"]
    bp_sys = vitals.get('bp_systolic', 0)
    bp_dias = vitals.get('bp_diastolic', 0)
    
    if bp_sys >= 160 or bp_dias >= 110 or len(ai_input["symptoms"]) >= 4:
        ai_input["assessment_type"] = "emergency"
    
    return ai_input
