"""
End-to-end offline PWA flow (Playwright, real browser + real server).

Run with the Flask server already up on :8000 and demo data seeded:
    venv\\Scripts\\python.exe -m pytest e2e/test_offline_flow.py -q

Flow:
 1. Login as the demo ASHA and open New Assessment.
 2. Go offline (context.set_offline) and submit -> queued in IndexedDB,
    sync chip shows "1 pending".
 3. Go back online -> the queue flushes automatically -> chip disappears.
 4. Verify exactly one assessment row landed for that submission.
"""

import os
import re
import time

import pytest
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL not configured"
)


def _login_asha(page):
    page.goto(BASE_URL + "/")
    page.fill("input[name='username']", "asha")
    page.fill("input[name='password']", "asha123")
    page.click("button[type='submit']")
    page.wait_for_url(re.compile(r".*/asha/dashboard.*"), timeout=15000)


def _count_for_notes(notes_marker: str) -> int:
    from app.repositories._sql import scalar

    return scalar(
        "select count(*) from assessments where asha_notes = :n", {"n": notes_marker}
    ) or 0


def test_offline_capture_syncs_once(page):
    marker = f"e2e-offline-{int(time.time())}"

    _login_asha(page)
    page.goto(BASE_URL + "/asha/dashboard/new-assessment")
    page.wait_for_selector("#mother-select option:nth-child(2)", state="attached", timeout=15000)

    # Fill the form
    page.select_option("#mother-select", index=1)
    page.fill("#bp-systolic", "118")
    page.fill("#bp-diastolic", "76")
    page.fill("#heart-rate", "82")
    page.fill("#weight", "58")
    page.fill("#notes", marker)

    # Go OFFLINE and submit -> must be queued, not lost
    page.context.set_offline(True)
    page.click("#submit-btn")
    page.wait_for_selector("#sync-chip", state="visible", timeout=10000)
    assert page.inner_text("#sync-count").strip() == "1"
    assert page.inner_text("#conn-text").strip().lower() == "offline"
    assert _count_for_notes(marker) == 0, "row must NOT exist while offline"

    # Go ONLINE -> queue flushes automatically (window 'online' listener).
    # Generous timeout: the sync POST runs the full AI pipeline server-side and
    # Groq free-tier rate limits can add ~60s of retries.
    page.context.set_offline(False)
    page.wait_for_selector("#sync-chip", state="hidden", timeout=120000)

    # Exactly one row for this capture
    deadline = time.time() + 30
    while time.time() < deadline and _count_for_notes(marker) == 0:
        time.sleep(0.5)
    assert _count_for_notes(marker) == 1

    # Reload and confirm nothing re-syncs (idempotent, queue empty)
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    assert _count_for_notes(marker) == 1
    assert page.is_hidden("#sync-chip")
