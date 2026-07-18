"""
Admin Blueprint

Handles admin dashboard APIs for system governance.
Admins manage users, assignments, and view analytics.

URL Prefix: /admin
"""

from flask import Blueprint, current_app, jsonify, request
from app.repositories import mothers_repo, asha_repo, doctors_repo, assessments_repo
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)


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


@admin_bp.route('/analytics', methods=['GET'])
def analytics():
    """
    System-wide analytics endpoint.
    
    Returns:
    - Total mothers registered
    - Total assessments completed
    - Risk distribution (LOW/MODERATE/HIGH)
    - ASHA/Doctor workload
    """
    try:
        # Get all mothers
        all_mothers = mothers_repo.list_all_active()
        total_mothers = len(all_mothers)
        
        # Get all assessments
        all_assessments = assessments_repo.list_all()
        total_assessments = len(all_assessments)
        
        # Calculate risk distribution
        risk_counts = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'CRITICAL': 0}
        for assessment in all_assessments:
            risk = _risk_of(assessment)
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
        
        # Get ASHA and Doctor counts
        all_asha = asha_repo.list_all()
        all_doctors = doctors_repo.list_all()
        
        # Calculate risk trend (last 7 days)
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
        
        return jsonify({
            "total_mothers": total_mothers,
            "total_asha": len(all_asha),
            "total_doctors": len(all_doctors),
            "total_assessments": total_assessments,
            "risk_distribution": risk_counts,
            "risk_trend": risk_trend
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/mothers', methods=['GET'])
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

            # Get assigned ASHA name (memoized)
            asha_name = None
            aid = str(mother.get('assigned_asha_id') or '')
            if aid:
                if aid not in _asha_names:
                    asha = asha_repo.find_by_id(aid)
                    _asha_names[aid] = asha.get('name') if asha else None
                asha_name = _asha_names[aid]

            # Get assigned doctor name (memoized)
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
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/asha', methods=['GET'])
def get_asha():
    """Get all ASHA workers with workload statistics"""
    try:
        asha_workers = asha_repo.list_all()
        
        result = []
        for asha in asha_workers:
            asha_id_str = str(asha['_id'])
            
            # Count assigned mothers
            assigned_mothers = len(asha.get('assigned_mothers', []))
            
            # Count total assessments done
            all_assessments = assessments_repo.list_all()
            asha_assessments = [a for a in all_assessments if str(a.get('asha_id')) == asha_id_str]
            
            # Count high risk detected
            high_risk_count = len([a for a in asha_assessments
                                  if _risk_of(a) in ['HIGH', 'CRITICAL']])
            
            # Calculate performance badge
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
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/doctors', methods=['GET'])
def get_doctors():
    """Get all doctors with workload statistics"""
    try:
        doctors = doctors_repo.list_all()
        
        result = []
        for doctor in doctors:
            doctor_id_str = str(doctor['_id'])
            
            # Count assigned mothers
            assigned_mothers = len(doctor.get('assigned_mothers', []))
            
            # Count pending reviews (assessments flagged for doctor review)
            all_assessments = assessments_repo.list_all()
            pending_reviews = len([a for a in all_assessments 
                                  if a.get('requires_doctor_review') == True 
                                  and str(a.get('assigned_doctor_id')) == doctor_id_str
                                  and not a.get('doctor_reviewed')])
            
            # Calculate average response time (placeholder - would need review timestamps)
            avg_response_time = 0  # hours
            
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
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/assign', methods=['POST'])
def assign_worker():
    """
    Assign ASHA worker or doctor to a mother.
    
    Expected payload:
    {
        "mother_id": "ObjectId",
        "asha_id": "ObjectId" (optional),
        "doctor_id": "ObjectId" (optional)
    }
    """
    try:
        data = request.get_json()
        
        mother_id = data.get('mother_id')
        asha_id = data.get('asha_id')
        doctor_id = data.get('doctor_id')
        
        if not mother_id:
            return jsonify({"error": "mother_id is required"}), 400
        
        # Verify mother exists
        mother = mothers_repo.find_by_id(mother_id)
        if not mother:
            return jsonify({"error": "Mother not found"}), 404
        
        # Get old assignments for cleanup
        old_asha_id = mother.get('assigned_asha_id')
        old_doctor_id = mother.get('assigned_doctor_id')
        
        # Assign ASHA if provided
        if asha_id:
            asha = asha_repo.find_by_id(asha_id)
            if not asha:
                return jsonify({"error": "ASHA worker not found"}), 404
            
            # Remove from old ASHA's list
            if old_asha_id and str(old_asha_id) != asha_id:
                asha_repo.remove_mother_assignment(str(old_asha_id), mother_id)
            
            # Update mother's assigned ASHA
            mothers_repo.update(mother_id, {'assigned_asha_id': str(asha_id)})
            
            # Add to new ASHA's assigned list
            asha_repo.add_mother_assignment(asha_id, mother_id)
        
        # Assign doctor if provided
        if doctor_id:
            doctor = doctors_repo.find_by_id(doctor_id)
            if not doctor:
                return jsonify({"error": "Doctor not found"}), 404
            
            # Remove from old doctor's list
            if old_doctor_id and str(old_doctor_id) != doctor_id:
                doctors_repo.remove_mother_assignment(str(old_doctor_id), mother_id)
            
            # Update mother's assigned doctor
            mothers_repo.update(mother_id, {'assigned_doctor_id': str(doctor_id)})
            
            # Add to new doctor's assigned list
            doctors_repo.add_mother_assignment(doctor_id, mother_id)

        # Route the mother's earlier (unassigned-era) messages to the new care team
        # so they show up in the ASHA/doctor dashboards.
        try:
            from app.repositories import messages_repo
            routed = messages_repo.backfill_routing_for_mother(
                mother_id, asha_id=asha_id, doctor_id=doctor_id
            )
            if routed:
                current_app.logger.info(
                    f"[ASSIGN] Routed {routed} earlier message(s) from mother {mother_id} "
                    "to the newly assigned care team"
                )
        except Exception as e:
            current_app.logger.error(f"[ASSIGN] Message backfill failed: {e}")

        return jsonify({
            "status": "success",
            "message": "Assignment updated successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/asha', methods=['POST'])
def add_asha():
    """Register a new ASHA worker."""
    try:
        data = request.get_json()
        
        # Required fields in data
        required = ['name', 'phone', 'username', 'password', 'area']
        for field in required:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Check if username exists
        if asha_repo.get_by_username(data['username']):
            return jsonify({"error": "Username already exists"}), 400

        # Hash the password (never store plaintext)
        from app.security import hash_password
        data['password_hash'] = hash_password(data.pop('password'))

        # Create record
        asha_id = asha_repo.create(data)
        
        return jsonify({
            "status": "success",
            "message": "ASHA worker registered successfully",
            "asha_id": str(asha_id)
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/doctors', methods=['POST'])
def add_doctor():
    """Register a new doctor."""
    try:
        data = request.get_json()
        
        # Required fields
        required = ['name', 'phone', 'username', 'password', 'specialization']
        for field in required:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Check if username exists
        if doctors_repo.get_by_username(data['username']):
            return jsonify({"error": "Username already exists"}), 400

        # Hash the password (never store plaintext)
        from app.security import hash_password
        data['password_hash'] = hash_password(data.pop('password'))

        # Create record
        doctor_id = doctors_repo.create(data)
        
        return jsonify({
            "status": "success",
            "message": "Doctor registered successfully",
            "doctor_id": str(doctor_id)
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Admin blueprint"""
    return jsonify({
        "service": "admin",
        "status": "active"
    }), 200

