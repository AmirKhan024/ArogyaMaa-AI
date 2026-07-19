"""
Latency baseline for POST /asha/assessment.

Builds a representative payload from seeded data (real ASHA + assigned mother,
plausible vitals, two mild symptoms so the symptom agent makes a real LLM call
without triggering a CRITICAL alert storm), submits it with a fresh
client_uuid, and prints the server's per-stage timing breakdown.

Requires the target server to be running with PERF_DEBUG=true (the breakdown
is returned in the response as "_timings"), and .env with DATABASE_URL +
INTERNAL_API_TOKEN.

Usage:
    python scripts/measure_latency.py --port 8000 --label before_flask [--runs 1]

Cleanup of test rows:
    delete from assessments where asha_notes = 'latency baseline test';
"""

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402

from app.repositories import asha_repo, mothers_repo  # noqa: E402


def build_payload():
    asha = asha_repo.get_by_username("asha")
    if not asha:
        raise SystemExit("Seeded ASHA user 'asha' not found - run db/seed.py first")
    asha_id = str(asha["_id"])
    mothers = mothers_repo.list_by_asha(asha_id)
    if not mothers:
        raise SystemExit("No mothers assigned to seeded ASHA - run db/seed.py first")
    mother_id = str(mothers[0]["_id"])

    return {
        "asha_id": asha_id,
        "mother_id": mother_id,
        "client_uuid": str(uuid.uuid4()),
        "asha_notes": "latency baseline test",
        "vitals": {
            "bp_systolic": 118,
            "bp_diastolic": 76,
            "heart_rate": 82,
            "temperature": 98.4,
            "weight": 58.0,
            "hemoglobin": 11.2,
        },
        "symptoms": ["mild fatigue", "occasional backache"],
    }


def print_breakdown(timings, total_s):
    print("")
    print("%-32s %10s" % ("stage", "ms"))
    print("-" * 43)
    for t in timings:
        print("%-32s %10.1f" % (t["stage"], t["ms"]))
    print("-" * 43)
    print("%-32s %10.1f" % ("wall_total (client-side)", total_s * 1000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()

    token = os.getenv("INTERNAL_API_TOKEN")
    if not token:
        raise SystemExit("INTERNAL_API_TOKEN not set in .env")

    url = "http://127.0.0.1:%d/asha/assessment" % args.port
    results = []

    for i in range(args.runs):
        payload = build_payload()  # fresh client_uuid each run
        with httpx.Client(timeout=180) as client:
            import time
            t0 = time.perf_counter()
            resp = client.post(url, json=payload, headers={"X-Internal-Token": token})
            wall = time.perf_counter() - t0

        print("run %d: HTTP %d in %.2fs" % (i + 1, resp.status_code, wall))
        if resp.status_code != 201:
            print(resp.text[:1000])
            raise SystemExit("Unexpected status %d" % resp.status_code)

        body = resp.json()
        timings = body.get("_timings")
        if timings is None:
            raise SystemExit("No _timings in response - is the server running with PERF_DEBUG=true?")
        print_breakdown(timings, wall)
        results.append({
            "run": i + 1,
            "wall_s": round(wall, 3),
            "status": resp.status_code,
            "ai_evaluation_status": body.get("ai_evaluation_status"),
            "evaluation_method": (body.get("ai_evaluation") or {}).get("evaluation_method"),
            "timings": timings,
        })

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "baselines")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.label + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"label": args.label, "port": args.port, "results": results}, f, indent=2)
    print("")
    print("Saved baseline to %s" % out_path)


if __name__ == "__main__":
    main()
