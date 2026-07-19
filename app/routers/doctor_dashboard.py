"""Doctor Dashboard Router — FastAPI port of app/blueprints/doctor_dashboard/routes.py."""

import logging

from fastapi import APIRouter, Request
from starlette.responses import PlainTextResponse

from app.repositories import doctors_repo
from app.blueprints.shared_logic import get_clinical_portfolio_context
from app.routers._templating import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/doctor/dashboard")


def _get_doctor_name(doctor_id):
    """Helper to get doctor name from ID."""
    if not doctor_id:
        return 'Unknown'
    try:
        doctor = doctors_repo.get_by_id(doctor_id)
        return doctor.get('name', 'Unknown') if doctor else 'Unknown'
    except Exception:
        return 'Unknown'


@router.get("/", name="doctor_dashboard.dashboard")
def dashboard(request: Request, doctor_id: str = None):
    """Doctor main dashboard with overview statistics."""
    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)
    return render(request, 'doctor/dashboard.html', doctor_id=doctor_id, doctor_name=doctor_name)


@router.get("/mothers", name="doctor_dashboard.mothers")
def mothers(request: Request, doctor_id: str = None):
    """List of assigned mothers."""
    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)
    return render(request, 'doctor/mothers.html', doctor_id=doctor_id, doctor_name=doctor_name)


@router.get("/assessments", name="doctor_dashboard.assessments")
def assessments(request: Request, doctor_id: str = None, mother_id: str = ""):
    """Assessment history for a specific mother."""
    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)
    return render(request, 'doctor/assessments.html', doctor_id=doctor_id, mother_id=mother_id, doctor_name=doctor_name)


@router.get("/consultation/new", name="doctor_dashboard.consultation_form")
def consultation_form(request: Request, doctor_id: str = "", assessment_id: str = ""):
    """Create new consultation for an assessment."""
    doctor_name = _get_doctor_name(doctor_id)
    return render(request, 'doctor/consultation_form.html', doctor_id=doctor_id, assessment_id=assessment_id, doctor_name=doctor_name)


@router.get("/consultation/view", name="doctor_dashboard.consultation_view")
def consultation_view(request: Request, doctor_id: str = "", assessment_id: str = ""):
    """View consultation details (read-only)."""
    doctor_name = _get_doctor_name(doctor_id)
    return render(request, 'doctor/consultation_view.html', doctor_id=doctor_id, assessment_id=assessment_id, doctor_name=doctor_name)


@router.get("/message", name="doctor_dashboard.message")
def message(request: Request, doctor_id: str = None):
    """Send Telegram message to mother."""
    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)
    return render(request, 'doctor/message.html', doctor_id=doctor_id, doctor_name=doctor_name)


@router.get("/appointments", name="doctor_dashboard.appointments")
def appointments(request: Request, doctor_id: str = None):
    """Appointment requests booked by mothers via the Telegram bot."""
    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)
    return render(request, 'doctor/appointments.html', doctor_id=doctor_id, doctor_name=doctor_name)


@router.get("/documents", name="doctor_dashboard.view_documents")
def view_documents(request: Request, doctor_id: str = "", mother_id: str = ""):
    """View and review medical documents uploaded by ASHA workers."""
    doctor_name = _get_doctor_name(doctor_id)
    return render(request, 'doctor/documents.html', doctor_id=doctor_id, mother_id=mother_id, doctor_name=doctor_name)


@router.get("/ai-assistant", name="doctor_dashboard.ai_assistant")
def ai_assistant(request: Request, doctor_id: str = None):
    """AI Case Analysis Assistant for doctors."""
    from app.repositories import mothers_repo, assessments_repo

    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)

    # Get assigned mothers for this doctor with correct risk levels
    mothers = []
    try:
        if doctor_id:
            all_mothers = mothers_repo.list_by_doctor(doctor_id)
            for m in all_mothers:
                mother_id = m['_id']

                latest_assessments = assessments_repo.list_by_mother(mother_id, limit=1)

                risk_level = 'low'
                if latest_assessments:
                    latest = latest_assessments[0]
                    ai_eval = latest.get('ai_evaluation', {})
                    if ai_eval and ai_eval.get('risk_level'):
                        risk_level = ai_eval.get('risk_level', 'low').lower()
                    elif latest.get('risk_level'):
                        risk_level = latest.get('risk_level', 'low').lower()
                elif m.get('risk_level'):
                    risk_level = m.get('risk_level', 'low').lower()

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
        logger.error(f"Error fetching mothers: {e}")

    return render(request, 'doctor/ai_assistant.html', doctor_id=doctor_id, doctor_name=doctor_name, mothers=mothers)


@router.get("/patient/{mother_id}", name="doctor_dashboard.patient_profile")
def patient_profile(request: Request, mother_id: str, doctor_id: str = None):
    """View comprehensive clinical portfolio for a mother."""
    doctor_id = doctor_id or request.session.get('doctor_id', '')
    doctor_name = request.session.get('display_name') or _get_doctor_name(doctor_id)

    context = get_clinical_portfolio_context(mother_id)
    if not context:
        return PlainTextResponse("Patient Not Found", status_code=404)

    context['base_template'] = 'doctor/base.html'
    context['role_name'] = 'Doctor'
    context['doctor_id'] = doctor_id
    context['doctor_name'] = doctor_name

    return render(request, 'shared/patient_profile.html', **context)
