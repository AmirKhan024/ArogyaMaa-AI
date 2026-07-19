"""
Concurrency probe: N simultaneous requests, throughput + p50/p95.

Default mode "read" hits GET /asha/stats (web + DB concurrency, no Groq quota
burn). Mode "assessment" fires N full AI assessments with distinct
client_uuids - use sparingly (Groq rate limits).

Usage:
    python scripts/concurrency_test.py --port 8000 --n 5 --mode read
    python scripts/concurrency_test.py --port 8000 --n 10 --mode read
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402

from app.repositories import asha_repo, mothers_repo  # noqa: E402


def pctl(values, p):
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round(p / 100.0 * (len(values) - 1)))))
    return values[k]


async def run(args):
    token = os.getenv("INTERNAL_API_TOKEN")
    if not token:
        raise SystemExit("INTERNAL_API_TOKEN not set in .env")
    headers = {"X-Internal-Token": token}
    base = "http://127.0.0.1:%d" % args.port

    asha = asha_repo.get_by_username("asha")
    if not asha:
        raise SystemExit("Seeded ASHA user 'asha' not found - run db/seed.py first")
    asha_id = str(asha["_id"])

    async def one(client, i):
        t0 = time.perf_counter()
        try:
            if args.mode == "read":
                resp = await client.get(base + "/asha/stats", params={"asha_id": asha_id}, headers=headers)
            else:
                mothers = mothers_repo.list_by_asha(asha_id)
                payload = {
                    "asha_id": asha_id,
                    "mother_id": str(mothers[0]["_id"]),
                    "client_uuid": str(uuid.uuid4()),
                    "asha_notes": "latency baseline test",
                    "vitals": {"bp_systolic": 118, "bp_diastolic": 76, "heart_rate": 82,
                               "temperature": 98.4, "weight": 58.0, "hemoglobin": 11.2},
                    "symptoms": ["mild fatigue"],
                }
                resp = await client.post(base + "/asha/assessment", json=payload, headers=headers)
            elapsed = time.perf_counter() - t0
            return {"i": i, "status": resp.status_code, "s": elapsed}
        except Exception as e:
            return {"i": i, "status": "EXC:" + type(e).__name__, "s": time.perf_counter() - t0}

    t_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=300) as client:
        results = await asyncio.gather(*[one(client, i) for i in range(args.n)])
    wall = time.perf_counter() - t_start

    times = [r["s"] for r in results]
    ok = [r for r in results if r["status"] in (200, 201)]
    errors = [r for r in results if r not in ok]

    print("mode=%s n=%d port=%d" % (args.mode, args.n, args.port))
    print("wall time: %.2fs   throughput: %.2f req/s" % (wall, args.n / wall))
    print("per-request: min=%.2fs p50=%.2fs p95=%.2fs max=%.2fs"
          % (min(times), pctl(times, 50), pctl(times, 95), max(times)))
    print("ok=%d errors=%d" % (len(ok), len(errors)))
    for r in errors:
        print("  request %d -> %s after %.2fs" % (r["i"], r["status"], r["s"]))

    out = {
        "mode": args.mode, "n": args.n, "port": args.port,
        "wall_s": round(wall, 3), "throughput_rps": round(args.n / wall, 3),
        "p50_s": round(pctl(times, 50), 3), "p95_s": round(pctl(times, 95), 3),
        "min_s": round(min(times), 3), "max_s": round(max(times), 3),
        "ok": len(ok), "errors": len(errors),
    }
    if args.label:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "baselines")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, args.label + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print("Saved to %s" % path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--mode", choices=["read", "assessment"], default="read")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
