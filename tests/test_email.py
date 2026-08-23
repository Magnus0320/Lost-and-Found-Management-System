"""Mail delivery and the otp_debug exposure rule.

The security property under test: `otp_debug` is exposed if and only if
outbound mail is DISABLED. It must never appear when mail is enabled -- not
even when a send fails.
"""
from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.services.email_service import EmailService, MailDeliveryError


def _settings(**overrides):
    base = dict(
        DATABASE_URL="postgresql://u:p@localhost:5432/d",
        SECRET_KEY="test-secret",
        MAIL_ENABLED=False,
        MAIL_SERVER="smtp.gmail.com",
        MAIL_PORT=587,
        MAIL_USERNAME="sender@gmail.com",
        MAIL_PASSWORD="app-password-16c",
        MAIL_FROM="sender@gmail.com",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _service(**overrides) -> EmailService:
    svc = EmailService.__new__(EmailService)
    svc.settings = _settings(**overrides)
    return svc


# --- the enabled/disabled switch -------------------------------------------

def test_disabled_when_mail_enabled_is_false():
    assert _service(MAIL_ENABLED=False).enabled is False


def test_disabled_when_no_server_configured_even_if_enabled():
    """Belt and braces: MAIL_ENABLED=true with no server is still 'disabled'."""
    assert _service(MAIL_ENABLED=True, MAIL_SERVER=None).enabled is False


def test_enabled_when_switched_on_with_a_server():
    assert _service(MAIL_ENABLED=True).enabled is True


def test_disabled_send_returns_false_and_sends_nothing():
    with patch("smtplib.SMTP") as smtp:
        assert _service(MAIL_ENABLED=False).send("a@b.edu", "s", "b") is False
    smtp.assert_not_called()


# --- real send path ---------------------------------------------------------

def test_enabled_send_uses_starttls_login_and_returns_true():
    svc = _service(MAIL_ENABLED=True)
    conn = MagicMock()
    conn.send_message.return_value = {}  # no refused recipients
    with patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = conn
        assert svc.send("someone@example.edu", "Subject", "Body") is True
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
    conn.starttls.assert_called_once()
    conn.login.assert_called_once_with("sender@gmail.com", "app-password-16c")
    conn.send_message.assert_called_once()
    sent = conn.send_message.call_args[0][0]
    assert sent["To"] == "someone@example.edu"
    assert "sender@gmail.com" in sent["From"]


def test_starttls_skipped_when_disabled():
    svc = _service(MAIL_ENABLED=True, MAIL_USE_TLS=False)
    conn = MagicMock()
    conn.send_message.return_value = {}
    with patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = conn
        svc.send("a@b.edu", "s", "b")
    conn.starttls.assert_not_called()


def test_otp_body_carries_the_code_and_ttl():
    svc = _service(MAIL_ENABLED=True, OTP_TTL_MINUTES=7)
    conn = MagicMock()
    conn.send_message.return_value = {}
    with patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = conn
        svc.send_otp("a@b.edu", "424242", "registration")
    msg = conn.send_message.call_args[0][0]
    body = msg.get_content()
    assert "424242" in body and "7 minutes" in body
    assert msg["Subject"] == "Your registration code"


# --- failures are explicit, never silent ------------------------------------

@pytest.mark.parametrize(
    "exc,fragment",
    [
        (smtplib.SMTPAuthenticationError(535, b"bad creds"), "App Password"),
        (smtplib.SMTPSenderRefused(553, b"no", "sender@gmail.com"), "sender address"),
        (TimeoutError(), "Timed out"),
        (ConnectionRefusedError("refused"), "Could not connect"),
        (smtplib.SMTPException("boom"), "returned an error"),
    ],
)
def test_send_failures_raise_a_clear_error(exc, fragment):
    svc = _service(MAIL_ENABLED=True)
    with patch("smtplib.SMTP", side_effect=exc):
        with pytest.raises(MailDeliveryError) as caught:
            svc.send("a@b.edu", "s", "b")
    assert fragment in str(caught.value.detail)
    assert caught.value.status_code == 502


def test_refused_recipient_raises_rather_than_reporting_success():
    svc = _service(MAIL_ENABLED=True)
    conn = MagicMock()
    conn.send_message.return_value = {"a@b.edu": (550, b"No such user")}
    with patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = conn
        with pytest.raises(MailDeliveryError):
            svc.send("a@b.edu", "s", "b")


# --- THE security property --------------------------------------------------

def test_debug_code_exposed_only_when_mail_is_disabled():
    from app.services.auth_service import AuthService

    svc = AuthService.__new__(AuthService)

    svc.email = _service(MAIL_ENABLED=False)
    assert svc._debug_code("123456") == "123456", "dev mode must expose the code"

    svc.email = _service(MAIL_ENABLED=True)
    assert svc._debug_code("123456") is None, "enabled mail must never expose the code"


def test_debug_code_stays_hidden_when_mail_is_enabled_but_broken():
    """The regression this guards: keying otp_debug on delivery success would
    leak a live OTP exactly when SMTP is failing."""
    from app.services.auth_service import AuthService

    svc = AuthService.__new__(AuthService)
    svc.email = _service(MAIL_ENABLED=True)
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPAuthenticationError(535, b"nope")):
        with pytest.raises(MailDeliveryError):
            svc.email.send_otp("a@b.edu", "123456", "registration")
    assert svc._debug_code("123456") is None


def test_settings_default_to_mail_disabled():
    get_settings.cache_clear()
    s = _settings()
    assert s.mail_enabled is False
    assert s.mail_use_tls is True
    assert s.mail_port == 587
