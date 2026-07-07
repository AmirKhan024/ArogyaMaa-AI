"""
Smoke tests for the repository layer.

Requires a reachable Postgres via DATABASE_URL with db/schema.sql applied; skipped
otherwise. Verifies insert/read round-trips, the string ``_id`` alias, JSONB handling,
and client_uuid idempotency.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture(scope="module", autouse=True)
def _db():
    from app.db import init_db
    init_db()


def test_mother_create_and_id_alias():
    from app.db import new_uuid
    from app.repositories import mothers_repo
    cid = "test_" + new_uuid()[:8]
    mid = mothers_repo.create({
        "name": "Test Mother", "age": 27, "phone": "999",
        "telegram_chat_id": cid,
        "current_pregnancy": {"gestational_age_weeks": 20},
    })
    assert isinstance(mid, str)
    row = mothers_repo.get_by_telegram_chat_id(cid)
    assert row["_id"] == str(row["id"])                    # string _id alias
    assert row["current_pregnancy"]["gestational_age_weeks"] == 20  # JSONB round-trip


def test_assessment_client_uuid_idempotency():
    from app.db import new_uuid
    from app.repositories import mothers_repo, assessments_repo
    cid = "test_" + new_uuid()[:8]
    mid = mothers_repo.create({"name": "M", "telegram_chat_id": cid})
    cu = new_uuid()
    payload = {"mother_id": mid, "vitals": {"bp_systolic": 120}, "symptoms": [], "client_uuid": cu}
    a1 = assessments_repo.create(dict(payload))
    a2 = assessments_repo.create(dict(payload))  # replay must not duplicate
    assert a1 == a2
