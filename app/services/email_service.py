"""Outbound mail.

Two modes, chosen by ``MAIL_ENABLED``:

* **disabled** (dev/CI default) -- nothing is sent. The message is logged and
  ``send`` returns False, which is what lets the caller hand the OTP back to the
  client as ``otp_debug`` so the flow is exercisable without an SMTP server.
* **enabled** -- the message is delivered over real SMTP (STARTTLS on the
  submission port, i.e. smtp.gmail.com:587). A failure raises
  :class:`MailDeliveryError` with a specific, actionable message; it never fails
  silently, and it never falls back to returning the code to the client.

Security note
-------------
Whether ``otp_debug`` is exposed is decided by ``EmailService.enabled`` alone --
never by whether a particular send succeeded. Keying it on the delivery result
would leak a live OTP to the API caller the moment SMTP broke.
"""
from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.config import get_settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)


class MailDeliveryError(DomainError):
    """Raised when mail is enabled but the message could not be handed off."""

    status_code = 502


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        """True only when sending is switched on AND a server is configured."""
        return bool(self.settings.mail_enabled and self.settings.mail_server)

    # --- message construction -------------------------------------------
    def _build(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = formataddr(("Campus Lost & Found", self.settings.mail_from))
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain="campus-lost-found.local")
        message.set_content(body)
        return message

    # --- delivery --------------------------------------------------------
    def send(self, to: str, subject: str, body: str) -> bool:
        """Send a message.

        Returns True when handed to the SMTP server, False when mail is
        disabled. Raises :class:`MailDeliveryError` when mail is enabled but
        delivery failed -- callers must not treat that as "just skip it".
        """
        if not self.enabled:
            logger.info(
                "[mail disabled] would send to=%s subject=%r (set MAIL_ENABLED=true "
                "and MAIL_SERVER to deliver for real)", to, subject,
            )
            return False

        message = self._build(to, subject, body)
        server = self.settings.mail_server
        port = self.settings.mail_port

        try:
            with smtplib.SMTP(server, port, timeout=self.settings.mail_timeout_seconds) as smtp:
                smtp.ehlo()
                if self.settings.mail_use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if self.settings.mail_username and self.settings.mail_password:
                    smtp.login(self.settings.mail_username, self.settings.mail_password)
                # Empty dict == every recipient accepted.
                refused = smtp.send_message(message)

        except smtplib.SMTPAuthenticationError as exc:
            logger.error("SMTP authentication failed for %s@%s: %s",
                         self.settings.mail_username, server, exc)
            raise MailDeliveryError(
                "Email server rejected our credentials. For Gmail, MAIL_PASSWORD "
                "must be a 16-character App Password (with 2-Step Verification "
                "enabled), not the account password."
            ) from exc

        except smtplib.SMTPRecipientsRefused as exc:
            logger.error("SMTP recipient refused: %s", exc.recipients)
            raise MailDeliveryError(f"The mail server refused the address {to!r}.") from exc

        except smtplib.SMTPSenderRefused as exc:
            logger.error("SMTP sender refused: %s", exc)
            raise MailDeliveryError(
                f"The mail server refused the sender address {self.settings.mail_from!r}. "
                "For Gmail it must match the authenticated account."
            ) from exc

        except smtplib.SMTPNotSupportedError as exc:
            logger.error("SMTP feature unsupported on %s:%s: %s", server, port, exc)
            raise MailDeliveryError(
                f"{server}:{port} does not support the requested SMTP feature "
                f"({exc}). Check MAIL_PORT and MAIL_USE_TLS."
            ) from exc

        except (socket.timeout, TimeoutError) as exc:
            logger.error("SMTP timeout talking to %s:%s", server, port)
            raise MailDeliveryError(
                f"Timed out after {self.settings.mail_timeout_seconds}s connecting to "
                f"{server}:{port}."
            ) from exc

        except smtplib.SMTPException as exc:
            logger.error("SMTP error talking to %s:%s: %s", server, port, exc)
            raise MailDeliveryError(f"The mail server returned an error: {exc}") from exc

        # NB: keep this last -- smtplib.SMTPException also subclasses OSError.
        except (socket.gaierror, ConnectionError, OSError) as exc:
            logger.error("SMTP connection failure to %s:%s: %s", server, port, exc)
            raise MailDeliveryError(
                f"Could not connect to the mail server {server}:{port} ({exc})."
            ) from exc

        if refused:
            logger.error("SMTP partially refused: %s", refused)
            raise MailDeliveryError(f"The mail server refused these recipients: {refused}")

        logger.info("Sent %r to %s via %s:%s", subject, to, server, port)
        return True

    def send_otp(self, to: str, code: str, purpose: str) -> bool:
        label = purpose.replace("_", " ")
        return self.send(
            to=to,
            subject=f"Your {label} code",
            body=(
                f"Your verification code is {code}.\n"
                f"It expires in {self.settings.otp_ttl_minutes} minutes.\n\n"
                "If you did not request this, you can ignore this email.\n"
            ),
        )
