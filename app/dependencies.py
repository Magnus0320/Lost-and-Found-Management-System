"""Composition root.

Builds services from a request-scoped session so the routers never see a
``Session`` at all -- they only ever depend on a service object.
"""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db
from app.services.auth_service import AuthService
from app.services.claim_service import ClaimService
from app.services.item_service import ItemService
from app.services.location_service import LocationService
from app.services.notification_service import NotificationService

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    return ItemService(db)


def get_claim_service(db: Session = Depends(get_db)) -> ClaimService:
    return ClaimService(db)


def get_location_service(db: Session = Depends(get_db)) -> LocationService:
    return LocationService(db)


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        return auth.user_from_token_subject(payload.get("sub"))
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail
        ) from exc
