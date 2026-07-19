"""
Response-parity harness: Flask (:8000) vs FastAPI (:8001), same DB.

Logs into BOTH servers per role (form POST, separate cookie jars), fetches
each endpoint from both, and diffs status code, content type, JSON deep
equality (allowlist for volatile fields) and HTML bytes. This is the gate
that guarantees byte-identical behavior during the migration.

Usage:
    python scripts/diff_responses.py --groups api,admin,dashboards
    python scripts/diff_responses.py            (all groups)
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402

from app.repositories import asha_repo, doctors_repo, mothers_repo, documents_repo  # noqa: E402

FLASK = "http://127.0.0.1:8000"
FASTAPI = "http://127.0.0.1:8001"

# JSON keys whose values may legitimately differ between the two calls
# (server-generated timestamps etc.). Compared for presence only.
VOLATILE_KEYS = set()


def login(base, username, password):
    client = httpx.Client(base_url=base, timeout=60, follow_redirects=False)
    r = client.post("/", data={"username": username, "password": password})
    if r.status_code != 302:
        raise SystemExit("login as %s on %s failed: HTTP %d" % (username, base, r.status_code))
    return client


def strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: ("<volatile>" if k in VOLATILE_KEYS else strip_volatile(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def normalize_html(text):
    # Only normalization: collapse trailing whitespace per line (Jinja env
    # differences in newline handling).
    return re.sub(r"[ \t]+$", "", text, flags=re.M).strip()


def compare(name, ra, rb):
    problems = []
    if ra.status_code != rb.status_code:
        problems.append("status %d != %d" % (ra.status_code, rb.status_code))
    ct_a = (ra.headers.get("content-type") or "").split(";")[0]
    ct_b = (rb.headers.get("content-type") or "").split(";")[0]
    if ct_a != ct_b:
        problems.append("content-type %r != %r" % (ct_a, ct_b))
    if not problems:
        if ct_a == "application/json":
            ja, jb = strip_volatile(ra.json()), strip_volatile(rb.json())
            if ja != jb:
                problems.append("JSON differs")
                _dump_json_diff(name, ja, jb)
        elif ct_a.startswith("text/html"):
            if normalize_html(ra.text) != normalize_html(rb.text):
                problems.append("HTML differs")
                _dump_text_diff(name, normalize_html(ra.text), normalize_html(rb.text))
    return problems


def _dump_json_diff(name, ja, jb):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "baselines", "diff_" + re.sub(r"\W+", "_", name))
    with open(out + "_flask.json", "w", encoding="utf-8") as f:
        json.dump(ja, f, indent=2, sort_keys=True, default=str)
    with open(out + "_fastapi.json", "w", encoding="utf-8") as f:
        json.dump(jb, f, indent=2, sort_keys=True, default=str)


def _dump_text_diff(name, ta, tb):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "baselines", "diff_" + re.sub(r"\W+", "_", name))
    with open(out + "_flask.html", "w", encoding="utf-8") as f:
        f.write(ta)
    with open(out + "_fastapi.html", "w", encoding="utf-8") as f:
        f.write(tb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="all")
    args = ap.parse_args()
    groups = set(args.groups.split(",")) if args.groups != "all" else {"all"}

    def want(g):
        return "all" in groups or g in groups

    # Seeded context
    asha = asha_repo.get_by_username("asha")
    doctor = doctors_repo.get_by_username("doctor")
    if not asha or not doctor:
        raise SystemExit("Seeded users missing - run db/seed.py")
    asha_id = str(asha["_id"])
    doctor_id = str(doctor["_id"])
    mothers = mothers_repo.list_by_asha(asha_id)
    mother_id = str(mothers[0]["_id"]) if mothers else None
    docs = documents_repo.list_by_mother(mother_id) if mother_id else []
    document_id = str(docs[0]["_id"]) if docs else None

    admin_pass = os.getenv("ADMIN_PASSWORD")

    sessions = {}
    for role, creds in [("asha", ("asha", "asha123")), ("doctor", ("doctor", "doctor123"))]:
        sessions[role] = (login(FLASK, *creds), login(FASTAPI, *creds))
    if admin_pass:
        sessions["admin"] = (login(FLASK, os.getenv("ADMIN_USERNAME", "admin"), admin_pass),
                             login(FASTAPI, os.getenv("ADMIN_USERNAME", "admin"), admin_pass))

    checks = []  # (group, role, path)
    if want("api"):
        checks += [("api", "asha", "/api/health")]
        if document_id:
            checks += [("api", "asha", "/api/documents/" + document_id)]
    if want("admin") and "admin" in sessions:
        checks += [
            ("admin", "admin", "/admin/health"),
            ("admin", "admin", "/admin/analytics"),
            ("admin", "admin", "/admin/mothers"),
            ("admin", "admin", "/admin/asha"),
            ("admin", "admin", "/admin/doctors"),
        ]
    if want("dashboards"):
        checks += [
            ("dashboards", "admin", "/admin/dashboard/"),
            ("dashboards", "admin", "/admin/dashboard/mothers"),
            ("dashboards", "admin", "/admin/dashboard/asha"),
            ("dashboards", "admin", "/admin/dashboard/doctors"),
            ("dashboards", "asha", "/asha/dashboard/?asha_id=" + asha_id),
            ("dashboards", "asha", "/asha/dashboard/mothers?asha_id=" + asha_id),
            ("dashboards", "asha", "/asha/dashboard/new-assessment?asha_id=" + asha_id),
            ("dashboards", "asha", "/asha/dashboard/stats?asha_id=" + asha_id),
            ("dashboards", "asha", "/asha/dashboard/documents?asha_id=" + asha_id + ("&mother_id=" + mother_id if mother_id else "")),
            ("dashboards", "asha", "/asha/dashboard/notifications?asha_id=" + asha_id),
            ("dashboards", "asha", "/asha/dashboard/ai-assistant?asha_id=" + asha_id),
            ("dashboards", "doctor", "/doctor/dashboard/?doctor_id=" + doctor_id),
            ("dashboards", "doctor", "/doctor/dashboard/mothers?doctor_id=" + doctor_id),
            ("dashboards", "doctor", "/doctor/dashboard/message?doctor_id=" + doctor_id),
            ("dashboards", "doctor", "/doctor/dashboard/appointments?doctor_id=" + doctor_id),
            ("dashboards", "doctor", "/doctor/dashboard/ai-assistant?doctor_id=" + doctor_id),
        ]
        if mother_id:
            checks += [
                ("dashboards", "asha", "/asha/dashboard/patient/" + mother_id + "?asha_id=" + asha_id),
                ("dashboards", "doctor", "/doctor/dashboard/patient/" + mother_id + "?doctor_id=" + doctor_id),
                ("dashboards", "doctor", "/doctor/dashboard/assessments?doctor_id=" + doctor_id + "&mother_id=" + mother_id),
                ("dashboards", "asha", "/dashboard/shared/export/" + mother_id),
            ]
    if want("asha"):
        checks += [
            ("asha", "asha", "/asha/health"),
            ("asha", "asha", "/asha/mothers?asha_id=" + asha_id),
            ("asha", "asha", "/asha/stats?asha_id=" + asha_id),
            ("asha", "asha", "/asha/notifications/" + asha_id),
        ]
        if mother_id:
            checks += [("asha", "asha", "/asha/documents/" + mother_id)]
    if want("doctor"):
        checks += [
            ("doctor", "doctor", "/doctor/health"),
            ("doctor", "doctor", "/doctor/mothers?doctor_id=" + doctor_id),
            ("doctor", "doctor", "/doctor/assessments?doctor_id=" + doctor_id),
            ("doctor", "doctor", "/doctor/appointments?doctor_id=" + doctor_id),
            ("doctor", "doctor", "/doctor/messages?doctor_id=" + doctor_id),
        ]
    if want("rag"):
        checks += [
            ("rag", "asha", "/asha/rag/health"),
            ("rag", "asha", "/asha/rag/stats"),
            ("rag", "asha", "/asha/rag/threads?asha_id=" + asha_id),
        ]
    if want("doctor_ai"):
        checks += [("doctor_ai", "doctor", "/doctor/ai/health")]

    passed = failed = 0
    for group, role, path in checks:
        ca, cb = sessions[role]
        ra = ca.get(path)
        rb = cb.get(path)
        problems = compare(path, ra, rb)
        if problems:
            failed += 1
            print("FAIL [%s] %s : %s" % (group, path, "; ".join(problems)))
        else:
            passed += 1
            print("PASS [%s] %s (%d)" % (group, path, ra.status_code))

    print("")
    print("%d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
