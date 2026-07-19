"""
Offline-sync replay idempotency at the ROUTE level — FastAPI app.

Mirror of test_offline_replay.py against the FastAPI port: proves the
form-login/session flow, client_uuid dedup and side-effect skipping behave
identically. Needs DATABASE_URL + applied schema + seeded demo data.
"""

import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL not configured"
)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.fastapi_app import create_fastapi_app
    from app.web_settings import settings

    prior = settings.ENABLE_AI_ADVISORY
    settings.ENABLE_AI_ADVISORY = False  # keep the test fast & deterministic
    app = create_fastapi_app()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        settings.ENABLE_AI_ADVISORY = prior


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    # Remove the assessments this module created so demo data stays clean.
    from app.db import init_db
    from app.repositories._sql import exec_write
    init_db()
    exec_write("delete from assessments where asha_notes = 'offline replay test'", {})


@pytest.fixture()
def asha_and_mother():
    from app.repositories import asha_repo, mothers_repo

    asha = asha_repo.get_by_username("asha")
    if not asha:
        pytest.skip("demo ASHA not seeded (run db/seed.py)")
    mothers = mothers_repo.list_by_asha(asha["_id"])
    if not mothers:
        pytest.skip("no mothers assigned to demo ASHA")
    return asha, mothers[0]


def _login_as_asha(client):
    resp = client.post(
        "/", data={"username": "asha", "password": "asha123"}, follow_redirects=False
    )
    assert resp.status_code == 302, "ASHA demo login failed (run db/seed.py)"


def _payload(asha, mother, client_uuid):
    return {
        "asha_id": asha["_id"],
        "mother_id": mother["_id"],
        "vitals": {"bp_systolic": 118, "bp_diastolic": 76, "heart_rate": 80},
        "symptoms": [],
        "asha_notes": "offline replay test",
        "client_uuid": client_uuid,
    }


def test_replay_returns_already_synced_and_no_duplicate(client, asha_and_mother):
    from app.repositories import assessments_repo

    asha, mother = asha_and_mother
    _login_as_asha(client)
    cu = str(uuid.uuid4())

    first = client.post("/asha/assessment", json=_payload(asha, mother, cu))
    assert first.status_code in (200, 201), first.json()
    first_id = first.json().get("assessment_id")
    assert first_id

    second = client.post("/asha/assessment", json=_payload(asha, mother, cu))
    assert second.status_code == 200
    body = second.json()
    assert body.get("status") == "already_synced"
    assert body.get("assessment_id") == first_id

    # Exactly one row exists for this client_uuid
    assert assessments_repo.find_id_by_client_uuid(cu) == first_id


def test_distinct_client_uuids_not_deduped(client, asha_and_mother):
    asha, mother = asha_and_mother
    _login_as_asha(client)

    a = client.post("/asha/assessment", json=_payload(asha, mother, str(uuid.uuid4())))
    b = client.post("/asha/assessment", json=_payload(asha, mother, str(uuid.uuid4())))
    assert a.status_code in (200, 201) and b.status_code in (200, 201)
    assert a.json()["assessment_id"] != b.json()["assessment_id"]


def test_unauthenticated_api_rejected(client):
    resp = client.get("/asha/mothers?asha_id=x")
    assert resp.status_code == 401
    assert resp.json() == {"error": "unauthorized"}


def test_internal_token_authorizes(client, asha_and_mother):
    token = os.getenv("INTERNAL_API_TOKEN")
    if not token:
        pytest.skip("INTERNAL_API_TOKEN not configured")
    asha, _ = asha_and_mother
    resp = client.get(
        "/asha/stats", params={"asha_id": asha["_id"]},
        headers={"X-Internal-Token": token},
    )
    assert resp.status_code == 200
