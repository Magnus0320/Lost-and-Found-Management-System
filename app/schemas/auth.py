from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    roll_number: str = Field(..., min_length=1, max_length=20)
    batch: int = Field(..., ge=1950, le=2100)
    course: str = Field(..., max_length=10)
    branch: str = Field(..., max_length=10)


class VerifyRegistrationRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=8)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserResponse(ORMModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    roll_number: str
    batch: int
    course: str
    branch: str
    is_verified: bool
    is_admin: bool = False
    created_at: datetime


class PublicUserResponse(ORMModel):
    """Another user, as seen by someone who is not them.

    Contact details are withheld by default: ``contact_email`` has to be filled
    in deliberately by the caller (see ``of``), so a plain
    ``model_validate(user)`` -- which is what every list endpoint does -- can
    never leak an address by accident.

    It is disclosed at exactly one moment: once a claim is approved, the
    reporter and the claimant need to arrange the physical handover, so each
    can see the other's address. Withdrawing the approval takes it away again.
    """

    id: int
    first_name: str
    last_name: str
    contact_email: EmailStr | None = None

    @classmethod
    def of(cls, user, *, disclose_contact: bool = False) -> "PublicUserResponse":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            contact_email=user.email if disclose_contact else None,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserResponse


class RegistrationResponse(BaseModel):
    detail: str
    user: UserResponse
    otp_debug: str | None = Field(
        None,
        description=(
            "Present only when outbound mail is disabled (local/dev), so the "
            "verification flow is exercisable without an SMTP server."
        ),
    )


class PasswordResetRequestResponse(BaseModel):
    """Deliberately does not confirm whether the address exists."""

    detail: str
    otp_debug: str | None = Field(
        None,
        description="Present only when outbound mail is disabled (local/dev).",
    )
