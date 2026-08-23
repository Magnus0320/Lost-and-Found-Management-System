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
    created_at: datetime


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
