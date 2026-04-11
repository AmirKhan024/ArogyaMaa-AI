"""
Doctor Dashboard Routes

Web interface for doctors to review assessments and consultations.
"""

from flask import render_template, request, session
from . import doctor_dashboard_bp
from app.repositories import doctors_repo
from app.blueprints.shared_logic import get_clinical_portfolio_context


@doctor_dashboard_bp.route('/')
def dashboard():
    """
    Doctor main dashboard with overview statistics.
    
    Query params:
    - doctor_id: Doctor ID (required)
    """
    doctor_id = request.args.get('doctor_id') or session.get('doctor_id', '')
    doctor_name = session.get('display_name') or _get_doctor_name(doctor_id)
    return render_template('doctor/dashboard.html', doctor_id=doctor_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/mothers')
def mothers():
    """
    List of assigned mothers.
    
    Query params:
    - doctor_id: Doctor ID (required)
    """
    doctor_id = request.args.get('doctor_id') or session.get('doctor_id', '')
    doctor_name = session.get('display_name') or _get_doctor_name(doctor_id)
    return render_template('doctor/mothers.html', doctor_id=doctor_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/assessments')
def assessments():
    """
    Assessment history for a specific mother.
    
    Query params:
    - doctor_id: Doctor ID (required)
    - mother_id: Mother ID (required)
    """
    doctor_id = request.args.get('doctor_id') or session.get('doctor_id', '')
    mother_id = request.args.get('mother_id', '')
    doctor_name = session.get('display_name') or _get_doctor_name(doctor_id)
    return render_template('doctor/assessments.html', doctor_id=doctor_id, mother_id=mother_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/consultation/new')
def consultation_form():
    """
    Create new consultation for an assessment.
    
    Query params:
    - doctor_id: Doctor ID (required)
    - assessment_id: Assessment ID (required)
    """
    doctor_id = request.args.get('doctor_id', '')
    assessment_id = request.args.get('assessment_id', '')
    doctor_name = _get_doctor_name(doctor_id)
    return render_template('doctor/consultation_form.html', doctor_id=doctor_id, assessment_id=assessment_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/consultation/view')
def consultation_view():
    """
    View consultation details (read-only).
    
    Query params:
    - doctor_id: Doctor ID (required)
    - assessment_id: Assessment ID (required)
    """
    doctor_id = request.args.get('doctor_id', '')
    assessment_id = request.args.get('assessment_id', '')
    doctor_name = _get_doctor_name(doctor_id)
    return render_template('doctor/consultation_view.html', doctor_id=doctor_id, assessment_id=assessment_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/message')
def message():
    """
    Send Telegram message to mother.
    
    Query params:
    - doctor_id: Doctor ID (required)
    """
    doctor_id = request.args.get('doctor_id') or session.get('doctor_id', '')
    doctor_name = session.get('display_name') or _get_doctor_name(doctor_id)
    return render_template('doctor/message.html', doctor_id=doctor_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/documents')
def view_documents():
    """
    View and review medical documents uploaded by ASHA workers.
    
    Query params:
    - doctor_id: Doctor ID (required)
    - mother_id: Mother ID (required)
    """
    doctor_id = request.args.get('doctor_id', '')
    mother_id = request.args.get('mother_id', '')
    doctor_name = _get_doctor_name(doctor_id)
    return render_template('doctor/documents.html', doctor_id=doctor_id, mother_id=mother_id, doctor_name=doctor_name)


@doctor_dashboard_bp.route('/ai-assistant')
def ai_assistant():
    """
    AI Case Analysis Assistant for doctors.
    
    Query params:
    - doctor_id: Doctor ID (required)
    """
    from app.repositories import mothers_repo, assessments_repo
    
    doctor_id = request.args.get('doctor_id') or session.get('doctor_id', '')
    doctor_name = session.get('display_name') or _get_doctor_name(doctor_id)
    
    # Get assigned mothers for this doctor with correct risk levels
    mothers = []
    try:
        if doctor_id:
            # Use the existing list_by_doctor function
            all_mothers = mothers_repo.list_by_doctor(doctor_id)
            for m in all_mothers:
                mother_id = m['_id']
                
                # Get latest assessment for accurate risk level
                latest_assessments = assessments_repo.list_by_mother(mother_id, limit=1)
                
                # Determine risk level from latest assessment or mother record
                risk_level = 'low'
                if latest_assessments:
                    latest = latest_assessments[0]
                    # Check ai_evaluation first, then assessment level
                    ai_eval = latest.get('ai_evaluation', {})
                    if ai_eval and ai_eval.get('risk_level'):
                        risk_level = ai_eval.get('risk_level', 'low').lower()
                    elif latest.get('risk_level'):
                        risk_level = latest.get('risk_level', 'low').lower()
                elif m.get('risk_level'):
                    risk_level = m.get('risk_level', 'low').lower()
                
                # Normalize risk level
                if risk_level in ['critical', 'high']:
                    risk_level = 'high'
                elif risk_level in ['moderate', 'medium']:
                    risk_level = 'moderate'
                else:
                    risk_level = 'low'
                
                mothers.append({
                    '_id': str(mother_id),
                    'name': m.get('name', 'Unknown'),
                    'age': m.get('age'),
                    'gestational_age': m.get('gestational_age'),
                    'risk_level': risk_level
                })
    except Exception as e:
        print(f"Error fetching mothers: {e}")
    
    return render_template('doctor/ai_assistant.html', doctor_id=doctor_id, doctor_name=doctor_name, mothers=mothers)


@doctor_dashboard_bp.route('/patient/<mother_id>')
def patient_profile(mother_id):
    """View comprehensive clinical portfolio for a mother."""
    doctor_id = request.args.get('doctor_id') or session.get('doctor_id', '')
    doctor_name = session.get('display_name') or _get_doctor_name(doctor_id)
    
    context = get_clinical_portfolio_context(mother_id)
    if not context:
        return "Patient Not Found", 404
        
    # Add role-specific info
    context['base_template'] = 'doctor/base.html'
    context['role_name'] = 'Doctor'
    context['doctor_id'] = doctor_id
    context['doctor_name'] = doctor_name
    
    return render_template('shared/patient_profile.html', **context)


def _get_doctor_name(doctor_id):
    """Helper to get doctor name from ID."""
    if not doctor_id:
        return 'Unknown'
    try:
        doctor = doctors_repo.get_by_id(doctor_id)
        return doctor.get('name', 'Unknown') if doctor else 'Unknown'
    except:
        return 'Unknown'
