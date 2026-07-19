"""
Doctor AI Assistant Router — FastAPI port of app/doctor/ai_api.py.

Reuses the original module's _build_case_from_db (imported, not duplicated).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body

from app.doctor.ai_api import _build_case_from_db
from app.doctor.ai_assistant import get_doctor_assistant
from app.routers._utils import json_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/doctor/ai")


@router.post("/analyze-case", name="doctor_ai.analyze_case")
def analyze_case(data: dict = Body(None)):
    """Analyze a maternal health case for the doctor."""
    try:
        if not data:
            return json_response({
                "status": "error",
                "message": "Request body required"
            }, 400)

        mother_id = data.get('mother_id')

        if mother_id:
            case_data = _build_case_from_db(mother_id)
            if not case_data:
                return json_response({
                    "status": "error",
                    "message": "Mother not found"
                }, 404)
        else:
            # Use provided case data directly
            case_data = data

        # Validate minimum data
        if not case_data.get('current_vitals') and not case_data.get('mother_info'):
            assistant = get_doctor_assistant()
            return json_response({
                "status": "success",
                "analysis": assistant.get_insufficient_data_response()
            }, 200)

        assistant = get_doctor_assistant()
        analysis = assistant.analyze_case(case_data)

        logger.info(f"Case analysis completed: urgency={analysis.get('urgency_level')}")

        return json_response({
            "status": "success",
            "analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, 200)

    except Exception as e:
        logger.error(f"Error analyzing case: {e}", exc_info=True)
        return json_response({
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        }, 500)


@router.get("/analyze-case/{mother_id}", name="doctor_ai.analyze_case_by_id")
def analyze_case_by_id(mother_id: str):
    """Analyze a specific mother's case by ID."""
    try:
        case_data = _build_case_from_db(mother_id)

        if not case_data:
            return json_response({
                "status": "error",
                "message": "Mother not found"
            }, 404)

        assistant = get_doctor_assistant()
        analysis = assistant.analyze_case(case_data)

        logger.info(f"Case analysis for mother {mother_id}: urgency={analysis.get('urgency_level')}")

        return json_response({
            "status": "success",
            "mother_id": mother_id,
            "analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, 200)

    except Exception as e:
        logger.error(f"Error analyzing case {mother_id}: {e}", exc_info=True)
        return json_response({
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        }, 500)


@router.post("/chat/{mother_id}", name="doctor_ai.chat_about_case")
def chat_about_case(mother_id: str, data: dict = Body(None)):
    """Chat with AI about a specific patient's case."""
    try:
        data = data or {}
        message = data.get('message', '').strip()

        if not message:
            return json_response({
                "status": "error",
                "message": "Message is required"
            }, 400)

        case_data = _build_case_from_db(mother_id)

        if not case_data:
            return json_response({
                "status": "error",
                "message": "Patient not found"
            }, 404)

        assistant = get_doctor_assistant()
        response = assistant.chat_about_case(case_data, message)

        logger.info(f"Chat response for mother {mother_id}: {message[:50]}...")

        return json_response({
            "status": "success",
            "response": response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, 200)

    except Exception as e:
        logger.error(f"Error in chat for {mother_id}: {e}", exc_info=True)
        return json_response({
            "status": "error",
            "message": f"Chat failed: {str(e)}"
        }, 500)


@router.get("/health", name="doctor_ai.health_check")
def health_check():
    """Health check endpoint for Doctor AI Assistant."""
    try:
        assistant = get_doctor_assistant()

        return json_response({
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
        }, 200)

    except Exception as e:
        return json_response({
            "status": "unhealthy",
            "error": str(e)
        }, 503)
