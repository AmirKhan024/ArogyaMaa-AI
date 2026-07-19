"""ASHA Dashboard Router — FastAPI port of app/blueprints/asha_dashboard/routes.py."""

from fastapi import APIRouter, Request
from starlette.responses import PlainTextResponse

from app.repositories import asha_repo
from app.blueprints.shared_logic import get_clinical_portfolio_context
from app.routers._templating import render

router = APIRouter(prefix="/asha/dashboard")


def _asha_ctx(request: Request, asha_id):
    """Resolve asha_id (query param else session) and display name."""
    asha_id = asha_id or request.session.get('asha_id', '')
    asha_name = request.session.get('display_name', '')
    if asha_id and not asha_name:
        asha = asha_repo.get_by_id(asha_id)
        if asha:
            asha_name = asha.get('name', '')
    return asha_id, asha_name


@router.get("/", name="asha_dashboard.dashboard")
def dashboard(request: Request, asha_id: str = None):
    """Main ASHA dashboard with summary statistics"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/dashboard.html', asha_id=asha_id, asha_name=asha_name)


@router.get("/mothers", name="asha_dashboard.mothers")
def mothers(request: Request, asha_id: str = None):
    """My mothers page - list of assigned mothers"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/mothers.html', asha_id=asha_id, asha_name=asha_name)


@router.get("/new-assessment", name="asha_dashboard.new_assessment")
def new_assessment(request: Request, asha_id: str = None):
    """New assessment form page"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/new_assessment.html', asha_id=asha_id, asha_name=asha_name)


@router.get("/stats", name="asha_dashboard.stats")
def stats(request: Request, asha_id: str = None):
    """My statistics page"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/stats.html', asha_id=asha_id, asha_name=asha_name)


@router.get("/documents", name="asha_dashboard.view_documents")
def view_documents(request: Request, asha_id: str = None, mother_id: str = ""):
    """View medical documents for a mother"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/view_documents.html',
                  asha_id=asha_id,
                  asha_name=asha_name,
                  mother_id=mother_id)


@router.get("/notifications", name="asha_dashboard.notifications")
def notifications(request: Request, asha_id: str = None):
    """View notifications and messages from doctors"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/notifications.html',
                  asha_id=asha_id,
                  asha_name=asha_name)


@router.get("/ai-assistant", name="asha_dashboard.rag_chatbot")
def rag_chatbot(request: Request, asha_id: str = None):
    """ASHA RAG AI Assistant chatbot interface"""
    asha_id, asha_name = _asha_ctx(request, asha_id)
    return render(request, 'asha/rag_chatbot.html',
                  asha_id=asha_id,
                  asha_name=asha_name)


@router.get("/patient/{mother_id}", name="asha_dashboard.patient_profile")
def patient_profile(request: Request, mother_id: str, asha_id: str = None):
    """View comprehensive clinical portfolio for a mother."""
    asha_id = asha_id or request.session.get('asha_id', '')
    asha_name = request.session.get('display_name', '')

    context = get_clinical_portfolio_context(mother_id)
    if not context:
        return PlainTextResponse("Patient Not Found", status_code=404)

    context['base_template'] = 'asha/base.html'
    context['role_name'] = 'ASHA Worker'
    context['asha_id'] = asha_id
    context['asha_name'] = asha_name

    return render(request, 'shared/patient_profile.html', **context)
