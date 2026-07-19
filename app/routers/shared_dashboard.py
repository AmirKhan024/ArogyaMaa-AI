"""Shared Dashboard Router — FastAPI port of app/blueprints/shared_dashboard/__init__.py."""

from datetime import datetime

from fastapi import APIRouter, Request
from starlette.responses import PlainTextResponse

from app.blueprints.shared_logic import get_clinical_portfolio_context
from app.routers._templating import render

router = APIRouter(prefix="/dashboard/shared")


@router.get("/export/{mother_id}", name="shared_dashboard.export_profile")
def export_profile(request: Request, mother_id: str):
    """Render a clean, printable medical report for a mother."""
    context = get_clinical_portfolio_context(mother_id)
    if not context:
        return PlainTextResponse("Patient Not Found", status_code=404)

    # Standard datetime for the template
    context['datetime'] = datetime

    return render(request, 'shared/patient_export.html', **context)
