"""One-shot Brevo SMTP smoke test: sends a test email to DOCTOR_EMAIL."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import email_service  # noqa: E402


def main():
    to = os.getenv("DOCTOR_EMAIL") or email_service.EMAIL_FROM
    print(f"Sending test email to {to} via {email_service.SMTP_HOST}:{email_service.SMTP_PORT} ...")
    ok = email_service.send_email(
        to,
        "ArogyaMaa email test",
        "<h2>ArogyaMaa</h2><p>Brevo SMTP is working. This is a test email.</p>",
        "ArogyaMaa: Brevo SMTP is working. This is a test email.",
    )
    print("SUCCESS" if ok else "FAILED (see log output above)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
