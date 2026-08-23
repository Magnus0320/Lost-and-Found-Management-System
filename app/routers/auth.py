from fastapi import APIRouter, Depends, status

from app.dependencies import get_auth_service, get_current_user
from app.db.models import User
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
    UserResponse,
    VerifyRegistrationRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an account and issue a verification code",
)
def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> RegistrationResponse:
    user, debug_otp = service.register(payload)
    return RegistrationResponse(
        detail="Registered. Check your email for the verification code.",
        user=UserResponse.model_validate(user),
        otp_debug=debug_otp,
    )


@router.post(
    "/verify-registration",
    response_model=UserResponse,
    summary="Confirm an account with its emailed OTP",
)
def verify_registration(
    payload: VerifyRegistrationRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    user = service.verify_registration(payload.email, payload.otp)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a JWT")
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user, token, expires = service.login(payload.email, payload.password)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=expires,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
    summary="Send a password-reset OTP",
)
def request_password_reset(
    payload: PasswordResetRequest,
    service: AuthService = Depends(get_auth_service),
) -> PasswordResetRequestResponse:
    debug_otp = service.request_password_reset(payload.email)
    return PasswordResetRequestResponse(
        detail="If that address is registered, a reset code has been sent.",
        otp_debug=debug_otp,
    )


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    summary="Set a new password using the reset OTP",
)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.confirm_password_reset(payload.email, payload.otp, payload.new_password)
    return MessageResponse(detail="Password updated. You can now log in.")


@router.get("/me", response_model=UserResponse, summary="Current authenticated user")
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
