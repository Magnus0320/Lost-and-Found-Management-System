"""Prove otp_debug is exposed ONLY when outbound mail is disabled.

Runs the real /auth/register endpoint twice against the same live database --
once with MAIL_ENABLED=false, once with MAIL_ENABLED=true -- and prints both
response bodies side by side.

With mail enabled, SMTP is stubbed at the transport layer so no real message is
sent; everything above the socket (the app, the endpoint, the response model)
runs exactly as in production.

Usage:  python scripts/verify_otp_exposure.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB = os.getenv("TEST_DATABASE_URL",
               "postgresql://lostfound:lostfound@localhost:5432/lostfound")


def register(mail_enabled: bool) -> tuple[int, dict]:
    for key in list(os.environ):
        if key.startswith("MAIL_"):
            del os.environ[key]
    os.environ["DATABASE_URL"] = DB
    os.environ["SECRET_KEY"] = "otp-exposure-check"
    os.environ["RUN_MIGRATIONS_ON_STARTUP"] = "false"
    os.environ["MAIL_ENABLED"] = "true" if mail_enabled else "false"
    os.environ["MAIL_SERVER"] = "smtp.gmail.com"
    os.environ["MAIL_USERNAME"] = "sender@gmail.com"
    os.environ["MAIL_PASSWORD"] = "stub-app-password"
    os.environ["MAIL_FROM"] = "sender@gmail.com"

    for mod in [m for m in sys.modules if m.startswith("app.")]:
        del sys.modules[mod]

    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import app

    get_settings.cache_clear()
    tag = uuid.uuid4().hex[:10]
    payload = {
        "email": f"exposure-{tag}@campus.edu", "password": "correct-horse-battery",
        "first_name": "Exp", "last_name": "Osure", "roll_number": f"R{tag[:8]}",
        "batch": 2026, "course": "BTECH", "branch": "CSE",
    }

    conn = MagicMock()
    conn.send_message.return_value = {}  # server accepted every recipient
    with patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = conn
        with TestClient(app) as client:
            r = client.post("/auth/register", json=payload)
        smtp_used = smtp.called
    print(f"    (SMTP transport invoked: {smtp_used})")
    return r.status_code, r.json()


def main() -> int:
    print("=" * 74)
    print("A. MAIL_ENABLED=false   (dev fallback -- CI and the e2e test rely on this)")
    print("=" * 74)
    code_a, body_a = register(False)
    print(f"    HTTP {code_a}")
    print(json.dumps(body_a, indent=2))

    print()
    print("=" * 74)
    print("B. MAIL_ENABLED=true    (real delivery)")
    print("=" * 74)
    code_b, body_b = register(True)
    print(f"    HTTP {code_b}")
    print(json.dumps(body_b, indent=2))

    print()
    print("=" * 74)
    print("VERDICT")
    print("=" * 74)
    checks = [
        ("mail DISABLED -> otp_debug present and is a 6-digit code",
         isinstance(body_a.get("otp_debug"), str) and body_a["otp_debug"].isdigit()
         and len(body_a["otp_debug"]) == 6),
        ("mail ENABLED  -> otp_debug is null",
         body_b.get("otp_debug") is None),
        ("mail ENABLED  -> no 6-digit code anywhere in the response body",
         not any(
             isinstance(v, str) and v.isdigit() and len(v) == 6
             for v in _walk(body_b)
         )),
        ("both responses otherwise succeed (HTTP 201)", code_a == 201 and code_b == 201),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {label}")
        ok &= passed
    print()
    print(f"  otp_debug with mail disabled : {body_a.get('otp_debug')!r}")
    print(f"  otp_debug with mail enabled  : {body_b.get('otp_debug')!r}")
    return 0 if ok else 1


def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


if __name__ == "__main__":
    raise SystemExit(main())
