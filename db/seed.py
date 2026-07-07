"""
Seed script for ArogyaMaa-AI (Postgres / Supabase).

Creates demo users (one doctor, one ASHA worker) with bcrypt-hashed passwords and a
couple of demo mothers assigned to them, then prints the demo credentials.

Usage:
    python db/seed.py

Prerequisites:
    * DATABASE_URL set in .env
    * db/schema.sql already applied to that database
"""

import os
import sys

# Make the project root importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.db import init_db  # noqa: E402
from app.repositories import asha_repo, doctors_repo, mothers_repo  # noqa: E402
from app.security import hash_password  # noqa: E402

DOCTOR = {"username": "doctor", "password": "doctor123", "name": "Dr. Meera Rao",
          "specialization": "Obstetrics", "phone": "9000000001"}
ASHA = {"username": "asha", "password": "asha123", "name": "Sunita Devi",
        "phone": "9000000002", "area": "Rampur", "district": "Varanasi", "state": "UP"}
ADMIN_HINT = ("admin", os.getenv("ADMIN_PASSWORD") or "(set ADMIN_PASSWORD in .env for dev admin login)")

MOTHERS = [
    {"name": "Priya Kumari", "age": 24, "phone": "9111100001",
     "telegram_chat_id": "demo_priya", "risk_level": "pending",
     "current_pregnancy": {"gestational_age_weeks": 28}},
    {"name": "Anjali Singh", "age": 31, "phone": "9111100002",
     "telegram_chat_id": "demo_anjali", "risk_level": "pending",
     "current_pregnancy": {"gestational_age_weeks": 22}},
]


def _get_or_create_doctor():
    existing = doctors_repo.get_by_username(DOCTOR["username"])
    if existing:
        return existing["_id"]
    return doctors_repo.create({
        "username": DOCTOR["username"],
        "password_hash": hash_password(DOCTOR["password"]),
        "name": DOCTOR["name"],
        "specialization": DOCTOR["specialization"],
        "phone": DOCTOR["phone"],
    })


def _get_or_create_asha():
    existing = asha_repo.get_by_username(ASHA["username"])
    if existing:
        return existing["_id"]
    return asha_repo.create({
        "username": ASHA["username"],
        "password_hash": hash_password(ASHA["password"]),
        "name": ASHA["name"],
        "phone": ASHA["phone"],
        "area": ASHA["area"],
        "district": ASHA["district"],
        "state": ASHA["state"],
    })


def main():
    init_db()
    print("Seeding ArogyaMaa demo data...\n")

    doctor_id = _get_or_create_doctor()
    asha_id = _get_or_create_asha()
    print(f"  doctor id: {doctor_id}")
    print(f"  asha id:   {asha_id}")

    for m in MOTHERS:
        existing = mothers_repo.get_by_telegram_chat_id(m["telegram_chat_id"])
        if existing:
            mother_id = existing["_id"]
        else:
            data = dict(m)
            data["assigned_asha_id"] = asha_id
            data["assigned_doctor_id"] = doctor_id
            mother_id = mothers_repo.create(data)
        asha_repo.add_mother_assignment(asha_id, mother_id)
        doctors_repo.add_mother_assignment(doctor_id, mother_id)
        print(f"  mother:    {m['name']} ({mother_id})")

    print("\n" + "=" * 50)
    print("DEMO CREDENTIALS")
    print("=" * 50)
    print(f"  Doctor  ->  username: {DOCTOR['username']}   password: {DOCTOR['password']}")
    print(f"  ASHA    ->  username: {ASHA['username']}     password: {ASHA['password']}")
    print(f"  Admin   ->  username: {ADMIN_HINT[0]}     password: {ADMIN_HINT[1]}")
    print("=" * 50)
    print("\nDone.")


if __name__ == "__main__":
    main()
