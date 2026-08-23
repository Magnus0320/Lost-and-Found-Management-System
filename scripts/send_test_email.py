"""Send a real registration OTP and print the SMTP server's response code.

Registers a throwaway account against the live API using the configured Gmail
credentials, capturing smtplib's protocol-level debug output so the server's
acceptance code (250) is visible.

    python scripts/send_test_email.py recipient@example.com

Confirms the mail server ACCEPTED the message for delivery. It does not, and
cannot, confirm the message arrived in the recipient's inbox.
"""
from __future__ import annotations

import io
import json
import os
import smtplib
import sys
import uuid
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RECIPIENT = sys.argv[1] if len(sys.argv) > 1 else None
if not RECIPIENT:
    print("usage: python scripts/send_test_email.py recipient@example.com")
    raise SystemExit(2)


def main() -> int:
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    print("SMTP configuration in effect")
    print(f"  MAIL_ENABLED   : {settings.mail_enabled}")
    print(f"  MAIL_SERVER    : {settings.mail_server}")
    print(f"  MAIL_PORT      : {settings.mail_port}")
    print(f"  MAIL_USE_TLS   : {settings.mail_use_tls}")
    print(f"  MAIL_USERNAME  : {settings.mail_username}")
    print(f"  MAIL_PASSWORD  : {'<set, %d chars>' % len(settings.mail_password) if settings.mail_password else '<unset>'}")
    print(f"  MAIL_FROM      : {settings.mail_from}")
    print(f"  RECIPIENT      : {RECIPIENT}")

    if not settings.mail_enabled:
        print("\nMAIL_ENABLED is false -- nothing would be sent. Aborting.")
        return 1

    from app.services.email_service import EmailService, MailDeliveryError

    service = EmailService()
    print(f"\nEmailService.enabled = {service.enabled}")

    # Capture smtplib's wire-level conversation (it writes to stderr).
    original_debuglevel = smtplib.SMTP.debuglevel
    smtplib.SMTP.debuglevel = 1
    buffer = io.StringIO()
    code = f"{uuid.uuid4().int % 1000000:06d}"

    print("\n--- SMTP transaction ---")
    try:
        with redirect_stderr(buffer):
            delivered = service.send_otp(RECIPIENT, code, "registration")
    except MailDeliveryError as exc:
        smtplib.SMTP.debuglevel = original_debuglevel
        print(buffer.getvalue())
        print(f"\nDELIVERY FAILED (typed error, not a crash):\n  {exc.detail}")
        return 1
    finally:
        smtplib.SMTP.debuglevel = original_debuglevel

    transcript = buffer.getvalue()
    for line in transcript.splitlines():
        # Never echo the base64 AUTH credential line.
        if line.strip().startswith("send:") and "AUTH" in line:
            print("send: 'AUTH PLAIN <redacted>'")
            continue
        if line.strip().startswith("reply:") or line.strip().startswith("send:") \
           or line.strip().startswith("connect:") or line.strip().startswith("data:"):
            print(line)
    print("--- end transaction ---")

    accept_lines = [
        l for l in transcript.splitlines()
        if "250 2.0.0 OK" in l or ("data:" in l and "250" in l)
    ]
    print(f"\nsend_otp returned: {delivered}")
    print(f"OTP actually emailed: {code}")
    if accept_lines:
        print("\nSERVER ACCEPTANCE:")
        for l in accept_lines:
            print(f"  {l.strip()}")
    print(
        "\nThis proves the mail server accepted the message for delivery.\n"
        "It does NOT prove inbox arrival -- only you can confirm that."
    )
    return 0 if delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())
