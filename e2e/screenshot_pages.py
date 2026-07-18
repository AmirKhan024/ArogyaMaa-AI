"""Screenshot all dashboard pages for visual review. Usage:
    venv\\Scripts\\python.exe e2e\\screenshot_pages.py [outdir]
Server must be running on :8000 with seeded demo data.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
OUT = sys.argv[1] if len(sys.argv) > 1 else "e2e/screens"

ROLES = {
    "admin": ("admin", "admin123", [
        ("admin_dashboard", "/admin/dashboard/"),
        ("admin_mothers", "/admin/dashboard/mothers"),
        ("admin_asha", "/admin/dashboard/asha"),
        ("admin_doctors", "/admin/dashboard/doctors"),
    ]),
    "asha": ("asha", "asha123", [
        ("asha_dashboard", "/asha/dashboard/"),
        ("asha_mothers", "/asha/dashboard/mothers"),
        ("asha_new_assessment", "/asha/dashboard/new-assessment"),
        ("asha_stats", "/asha/dashboard/stats"),
        ("asha_notifications", "/asha/dashboard/notifications"),
        ("asha_ai_assistant", "/asha/dashboard/ai-assistant"),
    ]),
    "doctor": ("doctor", "doctor123", [
        ("doctor_dashboard", "/doctor/dashboard/"),
        ("doctor_mothers", "/doctor/dashboard/mothers"),
        ("doctor_appointments", "/doctor/dashboard/appointments"),
        ("doctor_message", "/doctor/dashboard/message"),
        ("doctor_documents", "/doctor/dashboard/documents"),
        ("doctor_ai_assistant", "/doctor/dashboard/ai-assistant"),
    ]),
}


def main():
    os.makedirs(OUT, exist_ok=True)
    console_errors = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for role, (user, pw, pages) in ROLES.items():
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            errors = []
            page.on("console", lambda m, errs=errors: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.screenshot(path=f"{OUT}/login.png")
            page.fill("input[name='username']", user)
            page.fill("input[name='password']", pw)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")
            for name, path in pages:
                try:
                    page.goto(BASE + path)
                    page.wait_for_load_state("networkidle", timeout=20000)
                    time.sleep(1.2)  # allow charts to animate in
                    page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
                    print(f"OK   {name}")
                except Exception as e:
                    print(f"FAIL {name}: {e}")
            console_errors[role] = errors
            ctx.close()
        browser.close()
    for role, errs in console_errors.items():
        uniq = sorted(set(errs))
        print(f"\n[{role}] {len(uniq)} unique console errors")
        for e in uniq[:10]:
            print("  -", e[:200])


if __name__ == "__main__":
    main()
