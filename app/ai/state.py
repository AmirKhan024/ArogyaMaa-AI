"""
State Schema for LangGraph

Defines the state structure that flows through all agent nodes.
"""

from typing import TypedDict, List, Dict, Optional, Literal


class ArogyaMaaState(TypedDict, total=False):
    """
    State that flows through the LangGraph workflow.
    
    Each agent reads from and writes to this shared state.
    """
    # Input data
    assessment_id: str
    mother_id: str
    assessment_type: Literal["routine", "emergency", "follow_up"]
    vitals: Dict
    symptoms: List[str]
    risk_factors: List[str]
    gestational_week: int
    has_lab_results: bool
    has_uploaded_documents: bool
    historical_assessments: List[Dict]
    mother_profile: Dict
    
    # Agent outputs
    risk_stratification_result: Dict
    symptom_reasoning_result: Dict
    trend_analysis_result: Dict
    document_analysis_result: Dict
    nutrition_lifestyle_result: Dict  # Changed from nutrition_plan to match agents.py
    communication_result: Dict  # Changed from communication_output to match agents.py
    
    # Final orchestrator output
    orchestration_id: str
    overall_risk_level: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    confidence_score: float
    recommended_actions: List[Dict]
    requires_doctor_review: bool
    agents_invoked: List[str]
    timestamp: str
