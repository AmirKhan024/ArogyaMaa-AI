"""
Admin Router — FastAPI port of app/blueprints/admin/routes.py.

Admin dashboard APIs for system governance.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Body

from app.repositories import mothers_repo, asha_repo, doctors_repo, assessments_repo
from app.routers._utils import json_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")


def _risk_of(assessment):
    """Risk category of an assessment (lives under ai_evaluation.risk_category)."""
    return ((assessment.get('ai_evaluation') or {}).get('risk_category') or 'LOW').upper()


def _date_str_of(assessment):
    """YYYY-MM-DD of an assessment's timestamp (datetime or ISO string), or ''."""
    ts = assessment.get('timestamp') or assessment.get('created_at')
    if hasattr(ts, 'strftime'):
        return ts.strftime('%Y-%m-%d')
    if isinstance(ts, str):
        return ts[:10]
    return ''


@router.get("/analytics", name="admin.analytics")
def analytics():
    """System-wide analytics endpoint."""
    try:
        all_mothers = mothers_repo.list_all_active()
        total_mothers = len(all_mothers)

        all_assessments = assessments_repo.list_all()
        total_assessments = len(all_assessments)

        risk_counts = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'CRITICAL': 0}
        for assessment in all_assessments:
            risk = _risk_of(assessment)
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

        all_asha = asha_repo.list_all()
        all_doctors = doctors_repo.list_all()

        today = datetime.now()
        risk_trend = []
        for i in range(7, -1, -1):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')

            day_assessments = [a for a in all_assessments if _date_str_of(a) == date_str]

            risk_trend.append({
                'date': date.strftime('%b %d'),
                'low': len([a for a in day_assessments if _risk_of(a) == 'LOW']),
                'moderate': len([a for a in day_assessments if _risk_of(a) == 'MODERATE']),
                'high': len([a for a in day_assessments if _risk_of(a) == 'HIGH']),
                'critical': len([a for a in day_assessments if _risk_of(a) == 'CRITICAL'])
            })

        return json_response({
            "total_mothers": total_mothers,
            "total_asha": len(all_asha),
            "total_doctors": len(all_doctors),
            "total_assessments": total_assessments,
            "risk_distribution": risk_counts,
            "risk_trend": risk_trend
        }, 200)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.get("/mothers", name="admin.get_mothers")
def get_mothers():
    """Get all mothers with assigned ASHA and doctor details"""
    try:
        mothers = mothers_repo.list_all_active()

        # One bulk query + in-memory grouping instead of per-mother round-trips
        # (each pooler round-trip costs ~0.5s; N+1 made this page take >10s).
        latest_risk_by_mother = {}
        for a in assessments_repo.list_all():
            mid = str(a.get('mother_id'))
            current = latest_risk_by_mother.get(mid)
            ts = _date_str_of(a)
            if current is None or ts > current[0]:
                latest_risk_by_mother[mid] = (ts, _risk_of(a))

        _asha_names, _doctor_names = {}, {}

        result = []
        for mother in mothers:
            latest_risk = latest_risk_by_mother.get(str(mother['_id']), ('', 'LOW'))[1]

            asha_name = None
            aid = str(mother.get('assigned_asha_id') or '')
            if aid:
                if aid not in _asha_names:
                    asha = asha_repo.find_by_id(aid)
                    _asha_names[aid] = asha.get('name') if asha else None
                asha_name = _asha_names[aid]

            doctor_name = None
            did = str(mother.get('assigned_doctor_id') or '')
            if did:
                if did not in _doctor_names:
                    doctor = doctors_repo.find_by_id(did)
                    _doctor_names[did] = doctor.get('name') if doctor else None
                doctor_name = _doctor_names[did]

            result.append({
                '_id': str(mother['_id']),
                'name': mother.get('name'),
                'age': mother.get('age'),
                'phone': mother.get('phone'),
                'gestational_age_weeks': mother.get('current_pregnancy', {}).get('gestational_age_weeks') or mother.get('gestational_age'),
                'district': mother.get('address', {}).get('district') or mother.get('location', '').split(',')[-1].strip() if mother.get('location') else 'N/A',
                'village': mother.get('address', {}).get('village') or mother.get('location', '').split(',')[0].strip() if mother.get('location') else 'N/A',
                'current_risk': latest_risk,
                'assigned_asha_id': str(mother.get('assigned_asha_id')) if mother.get('assigned_asha_id') else None,
                'assigned_asha_name': asha_name,
                'assigned_doctor_id': str(mother.get('assigned_doctor_id')) if mother.get('assigned_doctor_id') else None,
                'assigned_doctor_name': doctor_name,
                'status': mother.get('status', 'active'),
                'registered_via': mother.get('registered_via', 'manual'),  # 'telegram' or 'manual'
                'telegram_chat_id': mother.get('telegram_chat_id'),
                'location': mother.get('location')
            })

        return json_response(result, 200)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.get("/asha", name="admin.get_asha")
def get_asha():
    """Get all ASHA workers with workload statistics"""
    try:
        asha_workers = asha_repo.list_all()

        result = []
        for asha in asha_workers:
            asha_id_str = str(asha['_id'])

            assigned_mothers = len(asha.get('assigned_mothers', []))

            all_assessments = assessments_repo.list_all()
            asha_assessments = [a for a in all_assessments if str(a.get('asha_id')) == asha_id_str]

            high_risk_count = len([a for a in asha_assessments
                                  if _risk_of(a) in ['HIGH', 'CRITICAL']])

            if assigned_mothers == 0:
                performance = 'No Assignments'
            elif len(asha_assessments) / max(assigned_mothers, 1) >= 2:
                performance = 'Good'
            elif len(asha_assessments) / max(assigned_mothers, 1) >= 1:
                performance = 'Moderate'
            else:
                performance = 'Needs Attention'

            result.append({
                '_id': str(asha['_id']),
                'name': asha.get('name'),
                'phone': asha.get('phone'),
                'area': asha.get('area'),
                'district': asha.get('district'),
                'assigned_mothers_count': assigned_mothers,
                'total_assessments': len(asha_assessments),
                'high_risk_detected': high_risk_count,
                'performance': performance
            })

        return json_response(result, 200)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.get("/doctors", name="admin.get_doctors")
def get_doctors():
    """Get all doctors with workload statistics"""
    try:
        doctors = doctors_repo.list_all()

        result = []
        for doctor in doctors:
            doctor_id_str = str(doctor['_id'])

            assigned_mothers = len(doctor.get('assigned_mothers', []))

            all_assessments = assessments_repo.list_all()
            pending_reviews = len([a for a in all_assessments
                                  if a.get('requires_doctor_review') == True
                                  and str(a.get('assigned_doctor_id')) == doctor_id_str
                                  and not a.get('doctor_reviewed')])

            avg_response_time = 0  # hours (placeholder - would need review timestamps)

            result.append({
                '_id': str(doctor['_id']),
                'name': doctor.get('name'),
                'specialization': doctor.get('specialization'),
                'phone': doctor.get('phone'),
                'hospital': doctor.get('hospital'),
                'assigned_mothers': assigned_mothers,
                'pending_reviews': pending_reviews,
                'avg_response_time': avg_response_time
            })

        return json_response(result, 200)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.post("/assign", name="admin.assign_worker")
def assign_worker(data: dict = Body(None)):
    """Assign ASHA worker or doctor to a mother."""
    try:
        data = data or {}

        mother_id = data.get('mother_id')
        asha_id = data.get('asha_id')
        doctor_id = data.get('doctor_id')

        if not mother_id:
            return json_response({"error": "mother_id is required"}, 400)

        mother = mothers_repo.find_by_id(mother_id)
        if not mother:
            return json_response({"error": "Mother not found"}, 404)

        old_asha_id = mother.get('assigned_asha_id')
        old_doctor_id = mother.get('assigned_doctor_id')

        if asha_id:
            asha = asha_repo.find_by_id(asha_id)
            if not asha:
                return json_response({"error": "ASHA worker not found"}, 404)

            if old_asha_id and str(old_asha_id) != asha_id:
                asha_repo.remove_mother_assignment(str(old_asha_id), mother_id)

            mothers_repo.update(mother_id, {'assigned_asha_id': str(asha_id)})

            asha_repo.add_mother_assignment(asha_id, mother_id)

        if doctor_id:
            doctor = doctors_repo.find_by_id(doctor_id)
            if not doctor:
                return json_response({"error": "Doctor not found"}, 404)

            if old_doctor_id and str(old_doctor_id) != doctor_id:
                doctors_repo.remove_mother_assignment(str(old_doctor_id), mother_id)

            mothers_repo.update(mother_id, {'assigned_doctor_id': str(doctor_id)})

            doctors_repo.add_mother_assignment(doctor_id, mother_id)

        # Route the mother's earlier (unassigned-era) messages to the new care team
        # so they show up in the ASHA/doctor dashboards.
        try:
            from app.repositories import messages_repo
            routed = messages_repo.backfill_routing_for_mother(
                mother_id, asha_id=asha_id, doctor_id=doctor_id
            )
            if routed:
                logger.info(
                    f"[ASSIGN] Routed {routed} earlier message(s) from mother {mother_id} "
                    "to the newly assigned care team"
                )
        except Exception as e:
            logger.error(f"[ASSIGN] Message backfill failed: {e}")

        return json_response({
            "status": "success",
            "message": "Assignment updated successfully"
        }, 200)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.post("/asha", name="admin.add_asha")
def add_asha(data: dict = Body(None)):
    """Register a new ASHA worker."""
    try:
        data = data or {}

        required = ['name', 'phone', 'username', 'password', 'area']
        for field in required:
            if not data.get(field):
                return json_response({"error": f"Missing required field: {field}"}, 400)

        if asha_repo.get_by_username(data['username']):
            return json_response({"error": "Username already exists"}, 400)

        # Hash the password (never store plaintext)
        from app.security import hash_password
        data['password_hash'] = hash_password(data.pop('password'))

        asha_id = asha_repo.create(data)

        return json_response({
            "status": "success",
            "message": "ASHA worker registered successfully",
            "asha_id": str(asha_id)
        }, 201)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.post("/doctors", name="admin.add_doctor")
def add_doctor(data: dict = Body(None)):
    """Register a new doctor."""
    try:
        data = data or {}

        required = ['name', 'phone', 'username', 'password', 'specialization']
        for field in required:
            if not data.get(field):
                return json_response({"error": f"Missing required field: {field}"}, 400)

        if doctors_repo.get_by_username(data['username']):
            return json_response({"error": "Username already exists"}, 400)

        # Hash the password (never store plaintext)
        from app.security import hash_password
        data['password_hash'] = hash_password(data.pop('password'))

        doctor_id = doctors_repo.create(data)

        return json_response({
            "status": "success",
            "message": "Doctor registered successfully",
            "doctor_id": str(doctor_id)
        }, 201)

    except Exception as e:
        return json_response({"error": str(e)}, 500)


@router.get("/health", name="admin.health")
def health():
    """Health check endpoint for Admin blueprint"""
    return json_response({
        "service": "admin",
        "status": "active"
    }, 200)
