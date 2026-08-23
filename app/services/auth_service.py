from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.security import (
    create_access_token,
    generate_otp,
    hash_otp,
    hash_password,
    verify_otp,
    verify_password,
)
from app.db.models import OtpPurpose, User
from app.repositories.otp_repo import OtpRepository
from app.repositories.user_repo import UserRepository
from app.services.email_service import EmailService


class AuthService:
    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.otps = OtpRepository(db)
        self.email = EmailService()
        self.settings = get_settings()

    # --- registration ---------------------------------------------------
    def register(self, payload) -> tuple[User, str | None]:
        if self.users.get_by_email(payload.email):
            raise ConflictError("An account with that email already exists.")

        user = self.users.create(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            roll_number=payload.roll_number,
            batch=payload.batch,
            course=payload.course.upper(),
            branch=payload.branch.upper(),
            is_verified=False,
        )
        code = self._issue_otp(user, OtpPurpose.REGISTRATION)
        # Raises MailDeliveryError if mail is enabled but delivery fails; that
        # aborts the request (and rolls back the new user) rather than silently
        # creating an account nobody can verify.
        self.email.send_otp(user.email, code, "registration")
        return user, self._debug_code(code)

    def verify_registration(self, email: str, otp: str) -> User:
        user = self._require_user(email)
        if user.is_verified:
            raise ConflictError("Account is already verified.")
        self._consume_otp(user, otp, OtpPurpose.REGISTRATION)
        return self.users.mark_verified(user)

    # --- login ----------------------------------------------------------
    def login(self, email: str, password: str) -> tuple[User, str, int]:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_verified:
            raise AuthenticationError("Account is not verified yet.")
        token = create_access_token(user.id)
        return user, token, self.settings.access_token_expire_minutes

    # --- password reset -------------------------------------------------
    def request_password_reset(self, email: str) -> str | None:
        user = self.users.get_by_email(email)
        if user is None:
            # Do not leak which addresses are registered.
            return None
        code = self._issue_otp(user, OtpPurpose.PASSWORD_RESET)
        self.email.send_otp(user.email, code, "password reset")
        return self._debug_code(code)

    def confirm_password_reset(self, email: str, otp: str, new_password: str) -> User:
        user = self._require_user(email)
        self._consume_otp(user, otp, OtpPurpose.PASSWORD_RESET)
        return self.users.set_password_hash(user, hash_password(new_password))

    # --- helpers --------------------------------------------------------
    def _debug_code(self, code: str) -> str | None:
        """The OTP to echo back to the caller, or None.

        Exposed ONLY when outbound mail is switched off -- i.e. when there is no
        other way for a developer to obtain the code. This is deliberately keyed
        on `email.enabled` and never on whether a given send succeeded: keying it
        on the delivery result would hand a live OTP to the API caller the moment
        SMTP broke, which is exactly when an attacker would want it.
        """
        return None if self.email.enabled else code

    def _require_user(self, email: str) -> User:
        user = self.users.get_by_email(email)
        if user is None:
            raise NotFoundError("No account found for that email.")
        return user

    def _issue_otp(self, user: User, purpose: OtpPurpose) -> str:
        code = generate_otp()
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            minutes=self.settings.otp_ttl_minutes
        )
        self.otps.create(
            user_id=user.id,
            code_hash=hash_otp(code),
            purpose=purpose,
            expires_at=expires_at,
        )
        return code

    def _consume_otp(self, user: User, otp: str, purpose: OtpPurpose) -> None:
        for token in self.otps.active_for_user(user.id, purpose):
            if verify_otp(otp, token.code_hash):
                self.otps.consume(token)
                return
        raise ValidationError("That code is invalid or has expired.")

    def user_from_token_subject(self, subject: str) -> User:
        try:
            user_id = int(subject)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("Malformed token subject.") from exc
        user = self.users.get(user_id)
        if user is None:
            raise AuthenticationError("Token refers to a user that no longer exists.")
        return user
