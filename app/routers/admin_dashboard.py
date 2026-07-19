"""Admin Dashboard Router — FastAPI port of app/blueprints/admin_dashboard/routes.py."""

from fastapi import APIRouter, Request

from app.routers._templating import render

router = APIRouter(prefix="/admin/dashboard")


@router.get("/", name="admin_dashboard.dashboard")
def dashboard(request: Request):
    """Main admin dashboard with analytics and KPIs"""
    return render(request, 'admin/dashboard.html')


@router.get("/mothers", name="admin_dashboard.mothers")
def mothers(request: Request):
    """Mothers management page with assignment controls"""
    return render(request, 'admin/mothers.html')


@router.get("/asha", name="admin_dashboard.asha")
def asha(request: Request):
    """ASHA workers overview page"""
    return render(request, 'admin/asha.html')


@router.get("/doctors", name="admin_dashboard.doctors")
def doctors(request: Request):
    """Doctors overview page"""
    return render(request, 'admin/doctors.html')
