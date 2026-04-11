"""
Admin Blueprint

Handles admin dashboard APIs for system governance.
Admins manage users, assignments, and view analytics.

URL Prefix: /admin
"""

from flask import Blueprint, jsonify, request
from app.repositories import mothers_repo, asha_repo, doctors_repo, assessments_repo
from bson import ObjectId
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)


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
            risk = assessment.get('risk_level', 'LOW')
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
            
            day_assessments = [a for a in all_assessments 
                             if a.get('created_at', datetime.min).strftime('%Y-%m-%d') == date_str]
            
            risk_trend.append({
                'date': date.strftime('%b %d'),
                'low': len([a for a in day_assessments if a.get('risk_level') == 'LOW']),
                'moderate': len([a for a in day_assessments if a.get('risk_level') == 'MODERATE']),
                'high': len([a for a in day_assessments if a.get('risk_level') == 'HIGH']),
                'critical': len([a for a in day_assessments if a.get('risk_level') == 'CRITICAL'])
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
        
        result = []
        for mother in mothers:
            # Get latest assessment for risk level
            assessments = assessments_repo.list_by_mother(str(mother['_id']))
            latest_risk = 'LOW'
            if assessments:
                latest_risk = assessments[0].get('risk_level', 'LOW')
            
            # Get assigned ASHA name
            asha_name = None
            if mother.get('assigned_asha_id'):
                asha = asha_repo.find_by_id(mother['assigned_asha_id'])
                if asha:
                    asha_name = asha.get('name')
            
            # Get assigned doctor name
            doctor_name = None
            if mother.get('assigned_doctor_id'):
                doctor = doctors_repo.find_by_id(mother['assigned_doctor_id'])
                if doctor:
                    doctor_name = doctor.get('name')
            
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
                                  if a.get('risk_level') in ['HIGH', 'CRITICAL']])
            
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
            mothers_repo.update(mother_id, {'assigned_asha_id': ObjectId(asha_id)})
            
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
            mothers_repo.update(mother_id, {'assigned_doctor_id': ObjectId(doctor_id)})
            
            # Add to new doctor's assigned list
            doctors_repo.add_mother_assignment(doctor_id, mother_id)
        
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
        from app.db import get_collection
        if get_collection('asha_workers').find_one({'username': data['username']}):
            return jsonify({"error": "Username already exists"}), 400
        
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
        from app.db import get_collection
        if get_collection('doctors').find_one({'username': data['username']}):
            return jsonify({"error": "Username already exists"}), 400
        
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

