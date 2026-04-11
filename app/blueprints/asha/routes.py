"""
ASHA Worker Blueprint

Handles ASHA worker dashboard APIs.
ASHA workers collect health data and trigger AI assessments.

URL Prefix: /asha
"""

from flask import Blueprint, request, jsonify, current_app
from bson import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from app.repositories import mothers_repo, assessments_repo, asha_repo, documents_repo, messages_repo, doctors_repo

# Try to import AI components, use fallback if unavailable
try:
    from app.ai import create_ArogyaMaa_graph
    from app.ai.helpers import build_ai_evaluation, prepare_assessment_for_ai
    from app.ai.document_analyzer import analyze_medical_document
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    current_app.logger.warning("[AI] LangGraph not available, using fallback") if current_app else None

from app.ai.fallback import build_fallback_ai_evaluation
from app.ai.alerts import send_ai_alerts

asha_bp = Blueprint('asha', __name__)


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


@asha_bp.route('/mothers', methods=['GET'])
def get_mothers():
    """
    Get list of mothers assigned to ASHA worker.
    
    Query params:
    - asha_id: ASHA worker ID (required)
    
    Returns:
    - List of assigned mothers with basic info
    """
    try:
        # Get ASHA ID from query params
        asha_id = request.args.get('asha_id')
        
        if not asha_id:
            return jsonify({
                "error": "asha_id is required"
            }), 400
        
        # Verify ASHA worker exists
        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return jsonify({
                "error": "ASHA worker not found"
            }), 404
        
        # Get assigned mothers
        mothers = mothers_repo.list_by_asha(asha_id)
        current_app.logger.info(f"Found {len(mothers) if mothers else 0} mothers for ASHA {asha_id}")
        
        # Format response
        mothers_list = []
        for i, mother in enumerate(mothers):
            current_app.logger.info(f"Processing mother {i}: {mother.get('_id') if mother else 'None'}")
            pregnancy = mother.get('current_pregnancy') or {}
            address = mother.get('address') or {}
            
            # Get assessments for this mother
            mother_assessments = assessments_repo.list_by_mother(str(mother['_id']), limit=100)
            
            # Get latest risk from most recent assessment
            current_risk = None
            last_assessment_date = None
            if mother_assessments:
                latest = mother_assessments[0]
                last_assessment_date = latest.get('timestamp')
                ai_eval = latest.get('ai_evaluation') or {}
                current_risk = ai_eval.get('risk_category')
            
            # Safely get datetime fields (may be str or datetime in DB)
            edd = pregnancy.get('edd') or pregnancy.get('edd_date')
            edd_iso = safe_isoformat(edd)

            registered_at = mother.get('registered_at') or mother.get('created_at')
            registered_at_iso = safe_isoformat(registered_at)

            # Resolve assigned doctor name
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
        
        return jsonify({
            "asha_id": asha_id,
            "asha_name": asha_worker.get('name'),
            "total_mothers": len(mothers_list),
            "mothers": mothers_list
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching mothers for ASHA: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch mothers",
            "details": str(e)
        }), 500


@asha_bp.route('/assessment', methods=['POST'])
def submit_assessment():
    """
    Submit new health assessment.
    
    Expected payload:
    {
        "asha_id": "ObjectId",
        "mother_id": "ObjectId",
        "vitals": {
            "bp_systolic": number,
            "bp_diastolic": number,
            "heart_rate": number,
            "temperature": number (optional),
            "weight_kg": number (optional),
            "glucose_mg_dl": number (optional),
            "hemoglobin_g_dl": number (optional)
        },
        "symptoms": ["string"],
        "asha_notes": "string" (optional),
        "gestational_age_at_assessment": number (optional)
    }
    
    Flow:
    1. Validate input
    2. Create assessment record in MongoDB
    3. Return assessment ID (AI evaluation to be done in future chunk)
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": "Request body is required"
            }), 400
        
        # Validate required fields
        required_fields = ['asha_id', 'mother_id', 'vitals']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                "error": "Missing required fields",
                "missing": missing_fields
            }), 400
        
        # Validate vitals has required measurements
        vitals = data.get('vitals', {})
        required_vitals = ['bp_systolic', 'bp_diastolic', 'heart_rate']
        missing_vitals = [v for v in required_vitals if v not in vitals]
        
        if missing_vitals:
            return jsonify({
                "error": "Missing required vital signs",
                "missing": missing_vitals
            }), 400
        
        # Convert IDs to ObjectId
        try:
            # Handle if already ObjectId or string
            asha_id_raw = data['asha_id']
            mother_id_raw = data['mother_id']
            
            asha_id = ObjectId(asha_id_raw) if not isinstance(asha_id_raw, ObjectId) else asha_id_raw
            mother_id = ObjectId(mother_id_raw) if not isinstance(mother_id_raw, ObjectId) else mother_id_raw
        except Exception as e:
            current_app.logger.error(f"ID conversion error: {e}, asha_id={data.get('asha_id')}, mother_id={data.get('mother_id')}")
            return jsonify({
                "error": "Invalid asha_id or mother_id format",
                "details": str(e)
            }), 400
        
        # Verify ASHA worker exists
        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return jsonify({
                "error": "ASHA worker not found"
            }), 404
        
        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return jsonify({
                "error": "Mother not found"
            }), 404
        
        # Verify mother is assigned to this ASHA
        if mother.get('assigned_asha_id') != asha_id:
            return jsonify({
                "error": "Mother is not assigned to this ASHA worker"
            }), 403
        
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
        
        assessment_id = assessments_repo.create(assessment_data)
        
        # Log the assessment
        current_app.logger.info(
            f"Assessment created: {assessment_id} for mother {mother_id} by ASHA {asha_id}"
        )
        
        # Get the created assessment to return details
        assessment = assessments_repo.get_by_id(assessment_id)
        
        # ============================================================
        # CHUNK 8C: AI EVALUATION
        # ============================================================
        ai_evaluation_status = "not_run"
        ai_error = None
        
        try:
            # Check if AI is enabled
            if current_app.config.get('ENABLE_AI_ADVISORY', True):
                current_app.logger.info(f"[AI] Running orchestration for assessment {assessment_id}")
                
                # Get historical assessments for trend analysis
                historical = assessments_repo.list_by_mother(mother_id, limit=10)
                # Exclude current assessment from history
                historical = [h for h in historical if str(h['_id']) != str(assessment_id)]
                
                # Try AI agent first, fallback to rule-based
                try:
                    if AI_AVAILABLE:
                        # Prepare input for AI
                        ai_input = prepare_assessment_for_ai(assessment, mother, historical)
                        
                        # Create and invoke LangGraph
                        graph = create_ArogyaMaa_graph()
                        ai_result = graph.invoke(ai_input)
                        
                        # Transform to ai_evaluation schema
                        ai_evaluation = build_ai_evaluation(ai_result)
                        current_app.logger.info("[AI] Using LangGraph AI evaluation")
                    else:
                        raise ImportError("LangGraph not available")
                        
                except Exception as ai_agent_error:
                    # Fallback to rule-based evaluation
                    current_app.logger.warning(f"[AI] LangGraph failed, using fallback: {ai_agent_error}")
                    ai_evaluation = build_fallback_ai_evaluation(assessment, mother, historical)
                
                # Save to database
                updated = assessments_repo.update_ai_evaluation(assessment_id, ai_evaluation)
                
                if updated:
                    ai_evaluation_status = "completed"
                    current_app.logger.info(
                        f"[AI] Evaluation saved: Risk={ai_evaluation['risk_category']}, "
                        f"Confidence={ai_evaluation['confidence']:.2f}"
                    )
                    
                    # ============================================================
                    # CHUNK 8D: SEND AI-DRIVEN TELEGRAM ALERTS
                    # ============================================================
                    try:
                        current_app.logger.info(f"[ALERTS] Triggering alerts for assessment {assessment_id}")
                        
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
                            current_app.logger.info(
                                f"[ALERTS] Alerts sent: "
                                f"Mother={mother_status}, "
                                f"ASHA={asha_status}, "
                                f"Doctor={doctor_status}"
                            )
                        else:
                            current_app.logger.warning("[ALERTS] Alert system returned None or invalid data")
                        
                    except Exception as alert_error:
                        # Fail silently - don't block assessment flow
                        current_app.logger.error(
                            f"[ALERTS] Error sending alerts (non-blocking): {alert_error}",
                            exc_info=True
                        )
                    # ============================================================
                    # END TELEGRAM ALERTS
                    # ============================================================
                    
                else:
                    ai_evaluation_status = "failed_to_save"
                    current_app.logger.warning(f"[AI] Failed to save evaluation for {assessment_id}")
            else:
                ai_evaluation_status = "disabled"
                current_app.logger.info("[AI] AI advisory disabled in config")
        
        except Exception as e:
            ai_error = str(e)
            ai_evaluation_status = "error"
            current_app.logger.error(f"[AI] Error during evaluation: {e}", exc_info=True)
        
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
            "ai_evaluation_status": ai_evaluation_status
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
                "requires_doctor_review": ai_eval.get('requires_doctor_review'),
                "recommended_actions": ai_eval.get('recommended_actions', []),
                "key_findings": ai_eval.get('key_findings', []),
                "agents_invoked": ai_eval.get('agents_invoked', [])
            }
            response_data["alerts_sent"] = True
        elif ai_evaluation_status == "error":
            response_data["ai_error"] = ai_error
            response_data["ai_evaluation"] = {
                "risk_category": "UNKNOWN",
                "risk_score": None,
                "recommended_actions": ["AI evaluation failed. Please review manually."]
            }
        
        return jsonify(response_data), 201
    
    except Exception as e:
        current_app.logger.error(f"Error submitting assessment: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to submit assessment",
            "details": str(e)
        }), 500


@asha_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    Get ASHA worker performance statistics.
    
    Query params:
    - asha_id: ASHA worker ID (required)
    
    Returns:
    - Total assessments
    - Risk distribution (placeholder values for now)
    - Recent activity
    """
    try:
        # Get ASHA ID from query params
        asha_id = request.args.get('asha_id')
        
        if not asha_id:
            return jsonify({
                "error": "asha_id is required"
            }), 400
        
        # Verify ASHA worker exists
        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return jsonify({
                "error": "ASHA worker not found"
            }), 404
        
        # Get list of assigned mothers
        mothers = mothers_repo.list_by_asha(asha_id)
        
        # Get ALL assessments for this ASHA worker
        all_assessments = assessments_repo.list_by_asha(asha_id, limit=1000)
        
        # Calculate real-time statistics
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
        
        # Get recent assessments for activity feed
        recent_assessments = all_assessments[:10]
        
        # Format recent assessments
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
        
        # Calculate last assessment date
        last_assessment_date = all_assessments[0].get('timestamp') if all_assessments else None
        
        return jsonify({
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
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching ASHA stats: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch statistics",
            "details": str(e)
        }), 500


@asha_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for ASHA blueprint"""
    return jsonify({
        "service": "asha",
        "status": "active"
    }), 200


@asha_bp.route('/upload-document', methods=['POST'])
def upload_document():
    """
    Upload medical document (lab report, scan, prescription, etc.)
    
    Expected form data:
        - file: Document file (image or PDF)
        - mother_id: Mother's ObjectId
        - asha_id: ASHA worker's ObjectId
        - document_type: Type (lab_report, ultrasound, prescription, xray, other)
        - description: Description provided by ASHA
        - analyze_with_ai: Boolean (optional, default True)
    
    Returns:
        - document_id: Created document ID
        - ai_analysis: AI analysis results (if enabled)
        - file_info: File metadata
    """
    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Get form data
        mother_id = request.form.get('mother_id')
        asha_id = request.form.get('asha_id')
        document_type = request.form.get('document_type')
        description = request.form.get('description', '')
        analyze_with_ai = request.form.get('analyze_with_ai', 'true').lower() == 'true'
        
        # Validate required fields
        if not all([mother_id, asha_id, document_type]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Convert IDs
        try:
            mother_id = ObjectId(mother_id)
            asha_id = ObjectId(asha_id)
        except Exception:
            return jsonify({"error": "Invalid ID format"}), 400
        
        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return jsonify({"error": "Mother not found"}), 404
        
        # Verify ASHA exists
        asha_worker = asha_repo.get_by_id(asha_id)
        if not asha_worker:
            return jsonify({"error": "ASHA worker not found"}), 404
        
        # Secure filename
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Validate file type
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf', '.gif'}
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"File type {file_ext} not supported. Use: {', '.join(allowed_extensions)}"}), 400
        
        # Create upload directory if not exists
        upload_dir = os.path.join(current_app.root_path, '..', 'uploads', 'documents')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{mother_id}_{timestamp}_{filename}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Save file
        file.save(file_path)
        current_app.logger.info(f"[UPLOAD] Saved document: {file_path}")
        
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
        current_app.logger.info(f"[UPLOAD] Document record created: {document_id}")
        
        # AI Analysis (if enabled and supported file type)
        ai_analysis_result = None
        if analyze_with_ai and file_ext in {'.jpg', '.jpeg', '.png', '.gif'}:
            try:
                current_app.logger.info(f"[UPLOAD] Starting AI analysis for document {document_id}")
                
                # Analyze document with AI
                ai_analysis_result = analyze_medical_document(
                    image_path=file_path,
                    document_type=document_type,
                    description=description
                )
                
                # Save AI analysis to database
                documents_repo.update_ai_analysis(document_id, ai_analysis_result)
                
                # Save extracted text separately for search
                if ai_analysis_result.get('extracted_text'):
                    documents_repo.update_extracted_text(
                        document_id, 
                        ai_analysis_result['extracted_text']
                    )
                
                current_app.logger.info(
                    f"[UPLOAD] AI analysis completed: "
                    f"{len(ai_analysis_result.get('key_findings', []))} findings, "
                    f"{len(ai_analysis_result.get('abnormal_values', []))} abnormalities"
                )
                
            except Exception as ai_error:
                current_app.logger.error(f"[UPLOAD] AI analysis failed: {ai_error}", exc_info=True)
                ai_analysis_result = {
                    "error": str(ai_error),
                    "key_findings": [],
                    "abnormal_values": [],
                    "clinical_summary": "AI analysis failed - manual review required",
                    "recommendations": ["Review document manually"]
                }
        
        # Return response
        return jsonify({
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
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"[UPLOAD] Error uploading document: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to upload document",
            "details": str(e)
        }), 500


@asha_bp.route('/documents/<mother_id>', methods=['GET'])
def get_mother_documents(mother_id):
    """
    Get all documents for a specific mother.
    
    Args:
        mother_id: Mother's ObjectId
    
    Returns:
        List of documents with metadata and AI analysis
    """
    try:
        # Verify mother exists
        mother = mothers_repo.get_by_id(mother_id)
        if not mother:
            return jsonify({"error": "Mother not found"}), 404
        
        # Get all documents
        documents = documents_repo.list_by_mother(mother_id)
        
        # Format response
        documents_list = []
        for doc in documents:
            file_meta = doc.get('file_metadata', {})
            ai_analysis = doc.get('ai_analysis')
            doctor_review = doc.get('doctor_review')
            
            # Build doctor review info with doctor name
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
        
        return jsonify({
            "mother_id": mother_id,
            "mother_name": mother.get('name'),
            "total_documents": len(documents_list),
            "documents": documents_list
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching documents: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch documents",
            "details": str(e)
        }), 500


@asha_bp.route('/notifications/<asha_id>', methods=['GET'])
def get_notifications(asha_id):
    """
    Get all notifications for an ASHA worker.
    Includes doctor reviews, system alerts, etc.
    """
    try:
        from app.db import get_collection
        
        # Get all messages TO this ASHA worker
        messages = messages_repo.list_by_recipient(asha_id, recipient_type='asha')
        
        notifications = []
        
        for msg in messages:
            # Get mother info
            mother = mothers_repo.get_by_id(msg.get('mother_id'))
            mother_name = mother.get('name') if mother else 'Unknown'
            
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
            else:
                # System notification
                notification['type'] = 'system'
                notification['title'] = msg.get('subject', 'System Notification')
                notification['preview'] = msg.get('message', '')[:150] + '...'
            
            notifications.append(notification)
        
        # Sort by timestamp (newest first)
        notifications.sort(key=lambda x: x['timestamp'] or '', reverse=True)
        
        return jsonify({
            "asha_id": asha_id,
            "total_notifications": len(notifications),
            "unread_count": sum(1 for n in notifications if not n['read']),
            "notifications": notifications
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error fetching notifications: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to fetch notifications",
            "details": str(e)
        }), 500


@asha_bp.route('/notifications/<notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    try:
        from app.db import get_collection
        messages = get_collection('messages')
        
        result = messages.update_one(
            {'_id': ObjectId(notification_id)},
            {'$set': {'read': True}}
        )
        
        return jsonify({
            "success": True,
            "modified": result.modified_count > 0
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error marking notification as read: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to mark as read",
            "details": str(e)
        }), 500


@asha_bp.route('/notifications/mark-all-read', methods=['POST'])
def mark_all_read():
    """Mark all notifications as read for an ASHA worker."""
    try:
        data = request.get_json()
        asha_id = data.get('asha_id')
        
        from app.db import get_collection
        messages = get_collection('messages')
        
        result = messages.update_many(
            {
                'to_asha_id': ObjectId(asha_id),
                'read': {'$ne': True}
            },
            {'$set': {'read': True}}
        )
        
        return jsonify({
            "success": True,
            "marked_count": result.modified_count
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Error marking all as read: {e}", exc_info=True)
        return jsonify({
            "error": "Failed to mark all as read",
            "details": str(e)
        }), 500

