"""
ASHA Router — FastAPI port of app/blueprints/asha/routes.py.

ASHA workers collect health data and trigger AI assessments. The
/asha/assessment endpoint is the offline-sync target: its client_uuid
idempotency, exact 400 bodies and 120s AI budget are client contracts
(see app/static/js/offline-queue.js) and must not change.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict
from werkzeug.utils import secure_filename

from app.instrumentation import stage, perf_debug_enabled
from app.repositories import mothers_repo, assessments_repo, asha_repo, documents_repo, messages_repo, doctors_repo
from app.routers._utils import json_response
from app.web_settings import settings

# Try to import AI components, use fallback if unavailable
try:
    from app.ai import create_ArogyaMaa_graph
    from app.ai.helpers import build_ai_evaluation, prepare_assessment_for_ai
    from app.ai.document_analyzer import analyze_medical_document
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

from app.ai.fallback import build_fallback_ai_evaluation, calculate_risk_score_fallback
from app.ai.alerts import send_ai_alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asha")

_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "documents"
)


def safe_isoformat(value):
    """Safely convert a datetime or string date to ISO format string.
    Handles mixed DB state where some records store dates as strings,
    others as datetime objects (e.g. from Telegram bot vs web registration)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value  # Already a string, return as-is
    if hasattr(value, 'isoformat'):
        return value.isoformat()  # datetime / date object
    return str(value)  # Fallback


class AssessmentSubmission(BaseModel):
    """Documents the /asha/assessment payload shape.

    Deliberately non-enforcing (all-optional, Any-typed, extra allowed): the
    offline queue drops items on exactly HTTP 400, so the endpoint's manual
    validation and its exact 400 bodies are a client contract this model must
    not alter.
    """
    model_config = ConfigDict(extra="allow")

    asha_id: Optional[Any] = None
    mother_id: Optional[Any] = None
    vitals: Optional[Any] = None
    symptoms: Optional[Any] = None
    asha_notes: Optional[Any] = None
    gestational_age_at_assessment: Optional[Any] = None
    documents_uploaded: Optional[Any] = None
    client_uuid: Optional[Any] = None


@router.get("/mothers", name="asha.get_mothers")
def get_mothers(asha_id: str = None):
    """Get list of mothers assigned to ASHA worker."""
    try:
        if not asha_id:
            return json_response({
                "error": "asha_id is required"
            }, 400)

        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return json_response({
                "error": "ASHA worker not found"
            }, 404)

        mothers = mothers_repo.list_by_asha(asha_id)
        logger.info(f"Found {len(mothers) if mothers else 0} mothers for ASHA {asha_id}")

        mothers_list = []
        for i, mother in enumerate(mothers):
            logger.info(f"Processing mother {i}: {mother.get('_id') if mother else 'None'}")
            pregnancy = mother.get('current_pregnancy') or {}
            address = mother.get('address') or {}

            mother_assessments = assessments_repo.list_by_mother(str(mother['_id']), limit=100)

            current_risk = None
            last_assessment_date = None
            if mother_assessments:
                latest = mother_assessments[0]
                last_assessment_date = latest.get('timestamp')
                ai_eval = latest.get('ai_evaluation') or {}
                current_risk = ai_eval.get('risk_category')

            edd = pregnancy.get('edd') or pregnancy.get('edd_date')
            edd_iso = safe_isoformat(edd)

            registered_at = mother.get('registered_at') or mother.get('created_at')
            registered_at_iso = safe_isoformat(registered_at)

            doctor_name = 'Not Assigned'
            doctor_id_raw = mother.get('assigned_doctor_id')
            if doctor_id_raw:
                try:
                    doctor = doctors_repo.get_by_id(str(doctor_id_raw))
                    if doctor:
                        doctor_name = doctor.get('name', 'Unknown Doctor')
                except Exception:
                    pass

            mothers_list.append({
                "mother_id": str(mother['_id']),
                "name": mother.get('name', 'Unknown'),
                "age": mother.get('age'),
                "phone": mother.get('phone'),
                "gestational_age_weeks": pregnancy.get('gestational_age_weeks') or mother.get('gestational_age'),
                "edd": edd_iso,
                "village": address.get('village'),
                "registered_at": registered_at_iso,
                "total_assessments": len(mother_assessments),
                "current_risk": current_risk,
                "last_assessment_date": safe_isoformat(last_assessment_date),
                "doctor_name": doctor_name
            })

        return json_response({
            "asha_id": asha_id,
            "asha_name": asha_worker.get('name'),
            "total_mothers": len(mothers_list),
            "mothers": mothers_list
        }, 200)

    except Exception as e:
        logger.error(f"Error fetching mothers for ASHA: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch mothers",
            "details": str(e)
        }, 500)


@router.post("/assessment", name="asha.submit_assessment")
def submit_assessment(payload: AssessmentSubmission = Body(None)):
    """Submit new health assessment (offline-sync target, idempotent on client_uuid)."""
    try:
        data = payload.model_dump(exclude_unset=True) if payload is not None else None

        if not data:
            return json_response({
                "error": "Request body is required"
            }, 400)

        # Validate required fields
        required_fields = ['asha_id', 'mother_id', 'vitals']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return json_response({
                "error": "Missing required fields",
                "missing": missing_fields
            }, 400)

        # Validate vitals has required measurements
        vitals = data.get('vitals', {})
        required_vitals = ['bp_systolic', 'bp_diastolic', 'heart_rate']
        missing_vitals = [v for v in required_vitals if v not in vitals]

        if missing_vitals:
            return json_response({
                "error": "Missing required vital signs",
                "missing": missing_vitals
            }, 400)

        # Sanity-check the vitals — reject physiologically impossible values so a
        # typo (e.g. BP 87/98, systolic below diastolic) can't corrupt risk scores.
        try:
            sys_bp = float(vitals['bp_systolic'])
            dia_bp = float(vitals['bp_diastolic'])
            hr = float(vitals['heart_rate'])
        except (TypeError, ValueError):
            return json_response({"error": "Vital signs must be numeric"}, 400)

        problems = []
        if sys_bp <= dia_bp:
            problems.append(
                f"Systolic BP ({sys_bp:g}) must be higher than diastolic ({dia_bp:g}) — "
                "please re-check the reading"
            )
        if not (60 <= sys_bp <= 260):
            problems.append(f"Systolic BP {sys_bp:g} is outside the plausible range (60–260)")
        if not (30 <= dia_bp <= 160):
            problems.append(f"Diastolic BP {dia_bp:g} is outside the plausible range (30–160)")
        if not (30 <= hr <= 220):
            problems.append(f"Heart rate {hr:g} is outside the plausible range (30–220)")
        weight = vitals.get('weight_kg') or vitals.get('weight')
        if weight is not None:
            try:
                if not (25 <= float(weight) <= 200):
                    problems.append(f"Weight {weight} kg is outside the plausible range (25–200)")
            except (TypeError, ValueError):
                problems.append("Weight must be numeric")
        if problems:
            return json_response({"error": "Implausible vital signs", "details": problems}, 400)

        # Normalize IDs to strings (Postgres uses UUID strings)
        try:
            asha_id = str(data['asha_id'])
            mother_id = str(data['mother_id'])
        except Exception as e:
            logger.error(f"ID normalization error: {e}, asha_id={data.get('asha_id')}, mother_id={data.get('mother_id')}")
            return json_response({
                "error": "Invalid asha_id or mother_id format",
                "details": str(e)
            }, 400)

        # Verify ASHA worker exists
        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return json_response({
                "error": "ASHA worker not found"
            }, 404)

        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return json_response({
                "error": "Mother not found"
            }, 404)

        # Verify mother is assigned to this ASHA
        if mother.get('assigned_asha_id') != asha_id:
            return json_response({
                "error": "Mother is not assigned to this ASHA worker"
            }, 403)

        # Get gestational age from mother's profile if not provided
        gestational_age = data.get('gestational_age_at_assessment')
        if not gestational_age:
            pregnancy = mother.get('current_pregnancy', {})
            gestational_age = pregnancy.get('gestational_age_weeks')

        # Create assessment record
        assessment_data = {
            'mother_id': mother_id,
            'asha_id': asha_id,
            'vitals': vitals,
            'symptoms': data.get('symptoms', []),
            'asha_notes': data.get('asha_notes', ''),
            'gestational_age_at_assessment': gestational_age,
            'documents_uploaded': data.get('documents_uploaded', [])
        }

        # Offline-first idempotency: field captures made without connectivity carry a
        # client-generated UUID so replays after sync never create duplicate rows.
        # If this capture was already ingested, return success WITHOUT re-running the
        # AI pipeline or re-sending alerts (side effects must be idempotent too).
        timings = []
        client_uuid = data.get('client_uuid')
        if client_uuid:
            with stage("db:idempotency_lookup", timings):
                existing_id = assessments_repo.find_id_by_client_uuid(client_uuid)
            if existing_id:
                logger.info(
                    f"Assessment replay deduped: client_uuid={client_uuid} -> {existing_id}"
                )
                return json_response({
                    "status": "already_synced",
                    "assessment_id": existing_id,
                }, 200)
            assessment_data['client_uuid'] = client_uuid

        with stage("db:create_assessment", timings):
            assessment_id = assessments_repo.create(assessment_data)

        # Log the assessment
        logger.info(
            f"Assessment created: {assessment_id} for mother {mother_id} by ASHA {asha_id}"
        )

        # Get the created assessment to return details
        with stage("db:get_assessment", timings):
            assessment = assessments_repo.get_by_id(assessment_id)

        # ============================================================
        # AI EVALUATION
        # ============================================================
        ai_evaluation_status = "not_run"
        ai_error = None

        try:
            # Check if AI is enabled
            if settings.ENABLE_AI_ADVISORY:
                logger.info(f"[AI] Running orchestration for assessment {assessment_id}")

                # Get historical assessments for trend analysis
                with stage("db:history_fetch", timings):
                    historical = assessments_repo.list_by_mother(mother_id, limit=10)
                # Exclude current assessment from history
                historical = [h for h in historical if str(h['_id']) != str(assessment_id)]

                # Try AI agent first, fallback to rule-based
                try:
                    if AI_AVAILABLE:
                        # Prepare input for AI
                        ai_input = prepare_assessment_for_ai(assessment, mother, historical)

                        # Invoke LangGraph with a HARD time budget. Groq 429s carry
                        # server-suggested backoffs that can spiral into an hour of
                        # retries across the agents — the request must never hang;
                        # after the budget we score with the rule-based fallback.
                        import concurrent.futures as _cf
                        graph = create_ArogyaMaa_graph()
                        _pool = _cf.ThreadPoolExecutor(max_workers=1)
                        try:
                            with stage("ai:graph_invoke_total", timings):
                                ai_result = _pool.submit(graph.invoke, ai_input).result(timeout=120)
                        finally:
                            # wait=False: never block the request on a stuck retry thread
                            _pool.shutdown(wait=False, cancel_futures=True)

                        timings.extend(ai_result.get("perf_timings", []))

                        # Transform to ai_evaluation schema
                        with stage("ai:build_evaluation", timings):
                            ai_evaluation = build_ai_evaluation(ai_result)
                        logger.info("[AI] Using LangGraph AI evaluation")
                    else:
                        raise ImportError("LangGraph not available")

                except Exception as ai_agent_error:
                    # Fallback to rule-based evaluation
                    logger.warning(f"[AI] LangGraph failed, using fallback: {ai_agent_error}")
                    ai_evaluation = build_fallback_ai_evaluation(assessment, mother, historical)

                # Save to database
                with stage("db:update_ai_evaluation", timings):
                    updated = assessments_repo.update_ai_evaluation(assessment_id, ai_evaluation)

                if updated:
                    ai_evaluation_status = "completed"
                    logger.info(
                        f"[AI] Evaluation saved: Risk={ai_evaluation['risk_category']}, "
                        f"Confidence={ai_evaluation['confidence']:.2f}"
                    )

                    # ============================================================
                    # SEND AI-DRIVEN TELEGRAM ALERTS
                    # ============================================================
                    try:
                        logger.info(f"[ALERTS] Triggering alerts for assessment {assessment_id}")

                        with stage("alerts:send", timings):
                            alert_results = send_ai_alerts(
                                assessment_id=assessment_id,
                                mother_id=mother_id,
                                ai_evaluation=ai_evaluation,
                                mother_data=mother,
                                asha_data=asha_worker
                            )

                        if alert_results and isinstance(alert_results, dict):
                            mother_status = alert_results.get('mother_alert', {}).get('status', 'unknown') if isinstance(alert_results.get('mother_alert'), dict) else 'unknown'
                            asha_status = alert_results.get('asha_alert', {}).get('status', 'unknown') if isinstance(alert_results.get('asha_alert'), dict) else 'unknown'
                            doctor_status = alert_results.get('doctor_alert', {}).get('status', 'unknown') if isinstance(alert_results.get('doctor_alert'), dict) else 'unknown'
                            logger.info(
                                f"[ALERTS] Alerts sent: "
                                f"Mother={mother_status}, "
                                f"ASHA={asha_status}, "
                                f"Doctor={doctor_status}"
                            )
                        else:
                            logger.warning("[ALERTS] Alert system returned None or invalid data")

                    except Exception as alert_error:
                        # Fail silently - don't block assessment flow
                        logger.error(
                            f"[ALERTS] Error sending alerts (non-blocking): {alert_error}",
                            exc_info=True
                        )
                    # ============================================================
                    # END TELEGRAM ALERTS
                    # ============================================================

                else:
                    ai_evaluation_status = "failed_to_save"
                    logger.warning(f"[AI] Failed to save evaluation for {assessment_id}")
            else:
                ai_evaluation_status = "disabled"
                logger.info("[AI] AI advisory disabled in config")

        except Exception as e:
            ai_error = str(e)
            ai_evaluation_status = "error"
            logger.error(f"[AI] Error during evaluation: {e}", exc_info=True)

        # ============================================================
        # END AI EVALUATION
        # ============================================================

        # Build response
        response_data = {
            "status": "success",
            "message": "Assessment submitted successfully",
            "assessment_id": str(assessment_id),
            "assessment_number": assessment.get('assessment_number'),
            "mother_name": mother.get('name'),
            "asha_name": asha_worker.get('name'),
            "timestamp": assessment.get('timestamp').isoformat() if assessment.get('timestamp') else None,
            "ai_evaluation_status": ai_evaluation_status,
            "client_uuid": client_uuid,
        }

        # Add AI results to response if completed
        if ai_evaluation_status == "completed":
            # Reload assessment with AI evaluation
            assessment_with_ai = assessments_repo.get_by_id(assessment_id)
            ai_eval = assessment_with_ai.get('ai_evaluation', {})

            response_data["ai_evaluation"] = {
                "risk_category": ai_eval.get('risk_category'),
                "risk_score": ai_eval.get('risk_score'),
                "confidence": ai_eval.get('confidence'),
                "evaluation_method": ai_eval.get('evaluation_method'),
                "requires_doctor_review": ai_eval.get('requires_doctor_review'),
                "recommended_actions": ai_eval.get('recommended_actions', []),
                "agents_invoked": ai_eval.get('agents_invoked', [])
            }
            response_data["alerts_sent"] = True
        elif ai_evaluation_status == "error":
            # Even a total AI failure must yield a real, vitals-driven risk number —
            # never a null score. The rule-based scorer needs no external services.
            response_data["ai_error"] = ai_error
            try:
                rb = calculate_risk_score_fallback(vitals, data.get('symptoms', []))
                response_data["ai_evaluation"] = {
                    "risk_category": rb['risk_category'],
                    "risk_score": rb['risk_score'],
                    "evaluation_method": "rule_based_fallback",
                    "recommended_actions": rb['recommended_actions'],
                }
            except Exception:
                response_data["ai_evaluation"] = {
                    "risk_category": "UNKNOWN",
                    "risk_score": 0,
                    "recommended_actions": ["AI evaluation failed. Please review manually."]
                }

        total_ms = round(sum(t["ms"] for t in timings if not t["stage"].startswith("node:")), 1)
        logger.info(
            "[PERF] assessment=%s total_ms=%s breakdown=%s",
            assessment_id, total_ms, json.dumps(timings)
        )
        if perf_debug_enabled():
            response_data["_timings"] = timings

        return json_response(response_data, 201)

    except Exception as e:
        logger.error(f"Error submitting assessment: {e}", exc_info=True)
        return json_response({
            "error": "Failed to submit assessment",
            "details": str(e)
        }, 500)


@router.get("/stats", name="asha.get_stats")
def get_stats(asha_id: str = None):
    """Get ASHA worker performance statistics."""
    try:
        if not asha_id:
            return json_response({
                "error": "asha_id is required"
            }, 400)

        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return json_response({
                "error": "ASHA worker not found"
            }, 404)

        mothers = mothers_repo.list_by_asha(asha_id)

        all_assessments = assessments_repo.list_by_asha(asha_id, limit=1000)

        risk_breakdown = {
            'LOW': 0,
            'MODERATE': 0,
            'HIGH': 0,
            'CRITICAL': 0,
            'NOT_EVALUATED': 0
        }

        high_risk_count = 0
        moderate_risk_count = 0
        low_risk_count = 0
        critical_risk_count = 0

        for assessment in all_assessments:
            ai_eval = assessment.get('ai_evaluation')
            if ai_eval:
                risk_category = ai_eval.get('risk_category', 'NOT_EVALUATED')
                risk_breakdown[risk_category] = risk_breakdown.get(risk_category, 0) + 1

                if risk_category == 'HIGH':
                    high_risk_count += 1
                elif risk_category == 'MODERATE':
                    moderate_risk_count += 1
                elif risk_category == 'LOW':
                    low_risk_count += 1
                elif risk_category == 'CRITICAL':
                    critical_risk_count += 1
            else:
                risk_breakdown['NOT_EVALUATED'] += 1

        recent_assessments = all_assessments[:10]

        recent_activity = []
        for assessment in recent_assessments[:5]:  # Last 5 assessments
            mother = mothers_repo.get_by_id(assessment['mother_id'])

            ai_eval = assessment.get('ai_evaluation')
            risk_info = {
                'risk_category': ai_eval.get('risk_category') if ai_eval else 'NOT_EVALUATED',
                'risk_score': ai_eval.get('risk_score') if ai_eval else None
            }

            recent_activity.append({
                'assessment_id': str(assessment['_id']),
                'mother_name': mother.get('name') if mother else 'Unknown',
                'timestamp': assessment.get('timestamp').isoformat() if assessment.get('timestamp') else None,
                'risk': risk_info,
                'symptoms_count': len(assessment.get('symptoms', []))
            })

        last_assessment_date = all_assessments[0].get('timestamp') if all_assessments else None

        return json_response({
            "asha_id": asha_id,
            "asha_name": asha_worker.get('name'),
            "area": asha_worker.get('area'),

            "statistics": {
                "total_mothers_assigned": len(mothers),
                "total_assessments": len(all_assessments),
                "high_risk_detected": high_risk_count,
                "moderate_risk_detected": moderate_risk_count,
                "low_risk_detected": low_risk_count,
                "critical_risk_detected": critical_risk_count,
                "last_assessment_date": last_assessment_date.isoformat() if last_assessment_date else None
            },

            "risk_breakdown": risk_breakdown,

            "recent_activity": recent_activity,

            "joined_at": asha_worker.get('joined_at').isoformat() if asha_worker.get('joined_at') else None
        }, 200)

    except Exception as e:
        logger.error(f"Error fetching ASHA stats: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch statistics",
            "details": str(e)
        }, 500)


@router.get("/health", name="asha.health")
def health():
    """Health check endpoint for ASHA blueprint"""
    return json_response({
        "service": "asha",
        "status": "active"
    }, 200)


@router.post("/upload-document", name="asha.upload_document")
def upload_document(
    file: UploadFile = File(None),
    mother_id: str = Form(None),
    asha_id: str = Form(None),
    document_type: str = Form(None),
    description: str = Form(""),
    analyze_with_ai: str = Form("true"),
):
    """Upload medical document (lab report, scan, prescription, etc.)"""
    try:
        # Validate file upload
        if file is None:
            return json_response({"error": "No file provided"}, 400)

        if not file.filename:
            return json_response({"error": "No file selected"}, 400)

        analyze_flag = (analyze_with_ai or "true").lower() == 'true'

        # Validate required fields
        if not all([mother_id, asha_id, document_type]):
            return json_response({"error": "Missing required fields"}, 400)

        # Normalize IDs to strings
        mother_id = str(mother_id)
        asha_id = str(asha_id)

        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return json_response({"error": "Mother not found"}, 404)

        # Verify ASHA exists
        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return json_response({"error": "ASHA worker not found"}, 404)

        # Secure filename
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()

        # Validate file type
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf', '.gif'}
        if file_ext not in allowed_extensions:
            return json_response({"error": f"File type {file_ext} not supported. Use: {', '.join(allowed_extensions)}"}, 400)

        # Create upload directory if not exists
        upload_dir = _UPLOAD_DIR
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{mother_id}_{timestamp}_{filename}"
        file_path = os.path.join(upload_dir, unique_filename)

        # Save file (stream to disk in chunks)
        with open(file_path, 'wb') as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        logger.info(f"[UPLOAD] Saved document: {file_path}")

        # File metadata
        file_size = os.path.getsize(file_path)
        file_metadata = {
            "original_filename": filename,
            "stored_filename": unique_filename,
            "file_path": file_path,
            "file_size_bytes": file_size,
            "file_type": file_ext,
            "mime_type": file.content_type
        }

        # Create document record
        document_data = {
            "mother_id": mother_id,
            "uploaded_by": "asha",
            "uploaded_by_id": asha_id,
            "document_type": document_type,
            "description": description,
            "file_metadata": file_metadata,
            "extracted_text": None,
            "ai_analysis": None
        }

        document_id = documents_repo.create(document_data)
        logger.info(f"[UPLOAD] Document record created: {document_id}")

        # AI Analysis (if enabled and supported file type)
        ai_analysis_result = None
        if analyze_flag and file_ext in {'.jpg', '.jpeg', '.png', '.gif'}:
            try:
                logger.info(f"[UPLOAD] Starting AI analysis for document {document_id}")

                ai_analysis_result = analyze_medical_document(
                    image_path=file_path,
                    document_type=document_type,
                    description=description
                )

                documents_repo.update_ai_analysis(document_id, ai_analysis_result)

                if ai_analysis_result.get('extracted_text'):
                    documents_repo.update_extracted_text(
                        document_id,
                        ai_analysis_result['extracted_text']
                    )

                logger.info(
                    f"[UPLOAD] AI analysis completed: "
                    f"{len(ai_analysis_result.get('key_findings', []))} findings, "
                    f"{len(ai_analysis_result.get('abnormal_values', []))} abnormalities"
                )

            except Exception as ai_error:
                logger.error(f"[UPLOAD] AI analysis failed: {ai_error}", exc_info=True)
                ai_analysis_result = {
                    "error": str(ai_error),
                    "key_findings": [],
                    "abnormal_values": [],
                    "clinical_summary": "AI analysis failed - manual review required",
                    "recommendations": ["Review document manually"]
                }

        # Return response
        return json_response({
            "success": True,
            "document_id": str(document_id),
            "file_info": {
                "filename": filename,
                "size_kb": round(file_size / 1024, 2),
                "type": document_type
            },
            "ai_analysis": ai_analysis_result,
            "message": "Document uploaded successfully" +
                      (" with AI analysis" if ai_analysis_result and not ai_analysis_result.get('error') else "")
        }, 200)

    except Exception as e:
        logger.error(f"[UPLOAD] Error uploading document: {e}", exc_info=True)
        return json_response({
            "error": "Failed to upload document",
            "details": str(e)
        }, 500)


@router.get("/documents/{mother_id}", name="asha.get_mother_documents")
def get_mother_documents(mother_id: str):
    """Get all documents for a specific mother."""
    try:
        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return json_response({"error": "Mother not found"}, 404)

        documents = documents_repo.list_by_mother(mother_id)

        documents_list = []
        for doc in documents:
            file_meta = doc.get('file_metadata', {})
            ai_analysis = doc.get('ai_analysis')
            doctor_review = doc.get('doctor_review')

            doctor_review_info = None
            if doctor_review:
                doctor_review_info = {
                    "reviewed": True,
                    "doctor_name": doctor_review.get('doctor_name', 'Unknown Doctor'),
                    "notes": doctor_review.get('notes'),
                    "reviewed_at": doctor_review.get('reviewed_at').isoformat() if doctor_review.get('reviewed_at') else None,
                    "ai_overridden": doctor_review.get('ai_overridden', False)
                }

            documents_list.append({
                "document_id": str(doc['_id']),
                "document_type": doc.get('document_type'),
                "description": doc.get('description', ''),
                "uploaded_at": doc.get('uploaded_at').isoformat() if doc.get('uploaded_at') else None,
                "uploaded_by": doc.get('uploaded_by'),
                "file_info": {
                    "filename": file_meta.get('original_filename'),
                    "size_kb": round(file_meta.get('file_size_bytes', 0) / 1024, 2),
                    "type": file_meta.get('file_type')
                },
                "has_ai_analysis": ai_analysis is not None,
                "ai_summary": ai_analysis.get('clinical_summary') if ai_analysis else None,
                "abnormal_count": len(ai_analysis.get('abnormal_values', [])) if ai_analysis else 0,
                "doctor_review": doctor_review_info
            })

        return json_response({
            "mother_id": mother_id,
            "mother_name": mother.get('name'),
            "total_documents": len(documents_list),
            "documents": documents_list
        }, 200)

    except Exception as e:
        logger.error(f"Error fetching documents: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch documents",
            "details": str(e)
        }, 500)


@router.post("/notifications/mark-all-read", name="asha.mark_all_read")
def mark_all_read(data: dict = Body(None)):
    """Mark all notifications as read for an ASHA worker."""
    try:
        data = data or {}
        asha_id = data.get('asha_id')

        marked_count = messages_repo.mark_all_notifications_read(asha_id)

        return json_response({
            "success": True,
            "marked_count": marked_count
        }, 200)

    except Exception as e:
        logger.error(f"Error marking all as read: {e}", exc_info=True)
        return json_response({
            "error": "Failed to mark all as read",
            "details": str(e)
        }, 500)


@router.get("/notifications/{asha_id}", name="asha.get_notifications")
def get_notifications(asha_id: str):
    """Get all notifications for an ASHA worker.
    Includes doctor reviews, system alerts, etc."""
    try:
        messages = messages_repo.list_by_recipient(asha_id, recipient_type='asha')

        notifications = []

        _mother_names = {}
        for msg in messages:
            # Get mother info (memoized — one pooler round-trip per unique mother)
            m_id = str(msg.get('mother_id') or '')
            if m_id and m_id not in _mother_names:
                mother = mothers_repo.get_by_id(m_id)
                _mother_names[m_id] = mother.get('name') if mother else 'Unknown'
            mother_name = _mother_names.get(m_id, 'Unknown')

            # Format notification
            notification = {
                "_id": str(msg['_id']),
                "mother_id": str(msg.get('mother_id')),
                "mother_name": mother_name,
                "timestamp": msg.get('timestamp').isoformat() if msg.get('timestamp') else None,
                "message": msg.get('message', ''),
                "read": msg.get('read', False)
            }

            # Determine notification type and format
            if msg.get('from_doctor'):
                notification['type'] = 'doctor_review'
                notification['doctor_name'] = msg.get('doctor_name', 'Doctor')

                if msg.get('document_id'):
                    # Doctor review of a document
                    doc = documents_repo.get_by_id(msg.get('document_id'))
                    doc_type = doc.get('document_type', 'document').replace('_', ' ').title() if doc else 'Document'

                    notification['title'] = f"Doctor Reviewed {doc_type}"
                    notification['preview'] = msg.get('message', '')[:150] + '...'
                    notification['document_id'] = str(msg.get('document_id'))
                    notification['document_type'] = doc_type
                else:
                    # General message from doctor
                    notification['title'] = f"Message from Dr. {msg.get('doctor_name', 'Doctor')}"
                    notification['preview'] = msg.get('message', '')[:150] + '...'
            elif msg.get('message_type') == 'from_mother':
                # Direct message from a mother (Telegram)
                notification['type'] = 'mother_message'
                notification['title'] = f"Message from {mother_name}"
                body = msg.get('content') or msg.get('message', '')
                notification['message'] = body
                notification['preview'] = body[:150]
            elif msg.get('is_alert') or msg.get('message_type') == 'ai_alert':
                # AI risk alert for one of this ASHA's mothers
                notification['type'] = 'ai_alert'
                notification['alert_type'] = msg.get('alert_type')
                notification['title'] = msg.get('subject') or f"AI risk alert — {mother_name}"
                body = msg.get('content') or msg.get('message', '')
                notification['message'] = body
                notification['preview'] = body[:150]
            else:
                # System notification
                notification['type'] = 'system'
                notification['title'] = msg.get('subject', 'System Notification')
                notification['preview'] = msg.get('message', '')[:150] + '...'

            notifications.append(notification)

        # Sort by timestamp (newest first)
        notifications.sort(key=lambda x: x['timestamp'] or '', reverse=True)

        return json_response({
            "asha_id": asha_id,
            "total_notifications": len(notifications),
            "unread_count": sum(1 for n in notifications if not n['read']),
            "notifications": notifications
        }, 200)

    except Exception as e:
        logger.error(f"Error fetching notifications: {e}", exc_info=True)
        return json_response({
            "error": "Failed to fetch notifications",
            "details": str(e)
        }, 500)


@router.post("/notifications/{notification_id}/read", name="asha.mark_notification_read")
def mark_notification_read(notification_id: str):
    """Mark a notification as read."""
    try:
        modified = messages_repo.mark_notification_read(notification_id)

        return json_response({
            "success": True,
            "modified": modified
        }, 200)

    except Exception as e:
        logger.error(f"Error marking notification as read: {e}", exc_info=True)
        return json_response({
            "error": "Failed to mark as read",
            "details": str(e)
        }, 500)
