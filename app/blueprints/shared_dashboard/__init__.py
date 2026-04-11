from flask import Blueprint, render_template, request, session, redirect, url_for
from datetime import datetime
from app.blueprints.shared_logic import get_clinical_portfolio_context

shared_dashboard_bp = Blueprint('shared_dashboard', __name__, url_prefix='/dashboard/shared')

@shared_dashboard_bp.route('/export/<mother_id>')
def export_profile(mother_id):
    """Render a clean, printable medical report for a mother."""
    context = get_clinical_portfolio_context(mother_id)
    if not context:
        return "Patient Not Found", 404
        
    # Standard datetime for the template
    context['datetime'] = datetime
    
    return render_template('shared/patient_export.html', **context)
