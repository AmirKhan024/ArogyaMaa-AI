"""
Doctor AI Assistant API - Flask Blueprint

REST API endpoints for Doctor Portal AI Assistant integration.
"""

from flask import Blueprint, request, jsonify
from bson import ObjectId
import logging
from datetime import datetime

from app.doctor.ai_assistant import get_doctor_assistant, DoctorAIAssistant

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
doctor_ai_bp = Blueprint('doctor_ai', __name__, url_prefix='/doctor/ai')


def get_db():
    """Get MongoDB database connection."""
    from app.db import get_db as get_mongo_db
    return get_mongo_db()


@doctor_ai_bp.route('/analyze-case', methods=['POST'])
def analyze_case():
    """
    Analyze a maternal health case for the doctor.
    
    Expected JSON body:
    {
        "mother_id": "ObjectId string",
        "doctor_id": "ObjectId string" (optional)
    }
    
    Or direct case data:
    {
        "mother_info": {...},
        "current_vitals": {...},
        "symptoms": [...],
        "gestational_age": 28,
        "historical_vitals": [...],
        "ai_risk_score": {...}
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "Request body required"
            }), 400
        
        # Check if mother_id provided - fetch from database
        mother_id = data.get('mother_id')
        
        if mother_id:
            case_data = _build_case_from_db(mother_id)
            if not case_data:
                return jsonify({
                    "status": "error",
                    "message": "Mother not found"
                }), 404
        else:
            # Use provided case data directly
            case_data = data
        
        # Validate minimum data
        if not case_data.get('current_vitals') and not case_data.get('mother_info'):
            assistant = get_doctor_assistant()
            return jsonify({
                "status": "success",
                "analysis": assistant.get_insufficient_data_response()
            }), 200
        
        # Get AI analysis
        assistant = get_doctor_assistant()
        analysis = assistant.analyze_case(case_data)
        
        logger.info(f"Case analysis completed: urgency={analysis.get('urgency_level')}")
        
        return jsonify({
            "status": "success",
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error analyzing case: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        }), 500


@doctor_ai_bp.route('/analyze-case/<mother_id>', methods=['GET'])
def analyze_case_by_id(mother_id):
    """
    Analyze a specific mother's case by ID.
    
    Path parameter:
        mother_id: MongoDB ObjectId of the mother
    """
    try:
        case_data = _build_case_from_db(mother_id)
        
        if not case_data:
            return jsonify({
                "status": "error",
                "message": "Mother not found"
            }), 404
        
        # Get AI analysis
        assistant = get_doctor_assistant()
        analysis = assistant.analyze_case(case_data)
        
        logger.info(f"Case analysis for mother {mother_id}: urgency={analysis.get('urgency_level')}")
        
        return jsonify({
            "status": "success",
            "mother_id": mother_id,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error analyzing case {mother_id}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        }), 500


@doctor_ai_bp.route('/chat/<mother_id>', methods=['POST'])
def chat_about_case(mother_id):
    """
    Chat with AI about a specific patient's case.
    
    Allows doctors to ask questions like:
    - Compare latest vs previous assessment
    - Summarize patient progress
    - Ask about specific symptoms or vitals
    
    Path parameter:
        mother_id: MongoDB ObjectId of the mother
        
    Body:
        message: The doctor's question
    """
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({
                "status": "error",
                "message": "Message is required"
            }), 400
        
        # Get full case data
        case_data = _build_case_from_db(mother_id)
        
        if not case_data:
            return jsonify({
                "status": "error",
                "message": "Patient not found"
            }), 404
        
        # Get AI response for the chat question
        assistant = get_doctor_assistant()
        response = assistant.chat_about_case(case_data, message)
        
        logger.info(f"Chat response for mother {mother_id}: {message[:50]}...")
        
        return jsonify({
            "status": "success",
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error in chat for {mother_id}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Chat failed: {str(e)}"
        }), 500


@doctor_ai_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Doctor AI Assistant."""
    try:
        assistant = get_doctor_assistant()
        
        return jsonify({
            "status": "healthy",
            "service": "Doctor AI Assistant",
            "model": assistant.model,
            "capabilities": [
                "case_analysis",
                "trend_detection",
                "abnormality_highlighting",
                "urgency_classification",
                "case_chat"
            ]
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503


def _build_case_from_db(mother_id: str) -> dict:
    """
    Build comprehensive case data from MongoDB for a specific mother.
    
    Fetches:
    - Mother information
    - Latest vitals from assessments
    - All symptoms
    - Historical vitals for trend analysis
    - AI risk scores and evaluations
    - Full assessment history
    """
    try:
        db = get_db()
        
        # Get mother information
        mother = db.mothers.find_one({"_id": ObjectId(mother_id)})
        if not mother:
            return None
        
        # Get ALL assessments sorted by timestamp (most recent first)
        all_assessments = list(db.assessments.find(
            {"mother_id": ObjectId(mother_id)}
        ).sort("timestamp", -1))
        
        latest_assessment = all_assessments[0] if all_assessments else None
        
        # Build case data
        case_data = {
            "mother_info": {
                "name": mother.get("name", "Unknown"),
                "age": mother.get("age"),
                "phone": mother.get("phone"),
                "blood_group": mother.get("blood_group"),
                "lmp": str(mother.get("lmp", "")) if mother.get("lmp") else None,
                "edd": str(mother.get("edd", "")) if mother.get("edd") else None
            },
            "gestational_age": mother.get("gestational_age"),
            "risk_level": mother.get("risk_level", "unknown"),
            "current_vitals": {},
            "symptoms": [],
            "historical_vitals": [],
            "ai_risk_score": {},
            "full_assessment_history": [],
            "latest_ai_evaluation": None
        }
        
        # Add current vitals and symptoms from latest assessment
        if latest_assessment:
            vitals = latest_assessment.get("vitals", {})
            case_data["current_vitals"] = {
                "bp_systolic": vitals.get("bp_systolic") or vitals.get("bp", "").split("/")[0] if "/" in str(vitals.get("bp", "")) else vitals.get("bp_systolic"),
                "bp_diastolic": vitals.get("bp_diastolic") or vitals.get("bp", "").split("/")[1] if "/" in str(vitals.get("bp", "")) else vitals.get("bp_diastolic"),
                "hemoglobin": vitals.get("hemoglobin"),
                "weight": vitals.get("weight"),
                "fetal_heart_rate": vitals.get("fetal_heart_rate") or vitals.get("heart_rate"),
                "pulse": vitals.get("pulse") or vitals.get("heart_rate"),
                "temperature": vitals.get("temperature"),
                "glucose": vitals.get("glucose"),
                "oxygen_saturation": vitals.get("oxygen_saturation") or vitals.get("spo2")
            }
            
            # Get symptoms from latest assessment
            case_data["symptoms"] = latest_assessment.get("symptoms", [])
            
            # Get AI evaluation if available
            ai_eval = latest_assessment.get("ai_evaluation", {})
            if ai_eval:
                case_data["latest_ai_evaluation"] = {
                    "risk_level": ai_eval.get("risk_level") or latest_assessment.get("risk_level"),
                    "risk_score": ai_eval.get("risk_score") or latest_assessment.get("risk_score"),
                    "recommendations": ai_eval.get("recommendations", []),
                    "reasoning": ai_eval.get("reasoning", ""),
                    "risk_flags": ai_eval.get("risk_flags", [])
                }
            
            # Fallback AI risk from assessment level
            case_data["ai_risk_score"] = {
                "category": latest_assessment.get("risk_level", "Unknown"),
                "score": latest_assessment.get("risk_score"),
                "flags": latest_assessment.get("risk_flags", [])
            }
            
            # Gestational age at latest assessment
            if latest_assessment.get("gestational_age_at_assessment"):
                case_data["gestational_age"] = latest_assessment.get("gestational_age_at_assessment")
        
        # Build complete historical record from ALL assessments
        for assessment in all_assessments:
            vitals = assessment.get("vitals", {})
            timestamp = assessment.get("timestamp") or assessment.get("created_at") or datetime.utcnow()
            
            # Historical vitals for trend analysis
            case_data["historical_vitals"].append({
                "date": timestamp.strftime("%Y-%m-%d") if hasattr(timestamp, 'strftime') else str(timestamp)[:10],
                "bp_systolic": vitals.get("bp_systolic"),
                "bp_diastolic": vitals.get("bp_diastolic"),
                "hemoglobin": vitals.get("hemoglobin"),
                "weight": vitals.get("weight"),
                "pulse": vitals.get("pulse") or vitals.get("heart_rate"),
                "glucose": vitals.get("glucose")
            })
            
            # Full assessment details
            ai_eval = assessment.get("ai_evaluation", {})
            case_data["full_assessment_history"].append({
                "assessment_id": str(assessment.get("_id")),
                "assessment_number": assessment.get("assessment_number"),
                "date": timestamp.strftime("%Y-%m-%d %H:%M") if hasattr(timestamp, 'strftime') else str(timestamp)[:16],
                "gestational_age_at_assessment": assessment.get("gestational_age_at_assessment"),
                "vitals": {
                    "bp": f"{vitals.get('bp_systolic', 'N/A')}/{vitals.get('bp_diastolic', 'N/A')} mmHg",
                    "hemoglobin": f"{vitals.get('hemoglobin', 'N/A')} g/dL" if vitals.get('hemoglobin') else "N/A",
                    "weight": f"{vitals.get('weight', 'N/A')} kg" if vitals.get('weight') else "N/A",
                    "glucose": f"{vitals.get('glucose', 'N/A')} mg/dL" if vitals.get('glucose') else "N/A",
                    "heart_rate": f"{vitals.get('pulse') or vitals.get('heart_rate', 'N/A')} bpm" if vitals.get('pulse') or vitals.get('heart_rate') else "N/A"
                },
                "symptoms": assessment.get("symptoms", []),
                "risk_level": assessment.get("risk_level") or (ai_eval.get("risk_level") if ai_eval else "Unknown"),
                "risk_score": assessment.get("risk_score") or (ai_eval.get("risk_score") if ai_eval else None),
                "ai_recommendations": ai_eval.get("recommendations", []) if ai_eval else [],
                "asha_notes": assessment.get("asha_notes", ""),
                "reviewed_by_doctor": assessment.get("reviewed_by_doctor", False)
            })
        
        # Reverse historical vitals so oldest first (for trend analysis)
        case_data["historical_vitals"].reverse()
        
        return case_data
        
    except Exception as e:
        logger.error(f"Error building case from DB: {e}", exc_info=True)
        return None
