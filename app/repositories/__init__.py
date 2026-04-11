"""
Repository Layer for ArogyaMaa

Clean data access layer for all MongoDB collections.
Import repositories from this package for use in blueprints and services.

Usage:
    from app.repositories import mothers_repo, assessments_repo
    
    mother = mothers_repo.get_by_id(mother_id)
    assessments = assessments_repo.list_by_mother(mother_id)
"""

from . import mothers_repo
from . import asha_repo
from . import doctors_repo
from . import assessments_repo
from . import consultations_repo
from . import documents_repo
from . import messages_repo
from . import registration_repo

__all__ = [
    'mothers_repo',
    'asha_repo',
    'doctors_repo',
    'assessments_repo',
    'consultations_repo',
    'documents_repo',
    'messages_repo',
    'registration_repo'
]
