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
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.claim_service import ClaimService
from app.services.item_service import ItemService
from app.services.location_service import LocationService
from app.services.notification_service import NotificationService

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_admin_service(db: Session = Depends(get_db)) -> AdminService:
    return AdminService(db)


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


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
) -> User | None:
    """The signed-in user, or None -- for routes that are public but show more
    to someone who is signed in.

    Deliberately never raises: browsing stays open to anyone, and a stale or
    malformed token degrades to "anonymous" rather than locking the page.
    """
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        return auth.user_from_token_subject(payload.get("sub"))
    except (jwt.PyJWTError, AuthenticationError):
        return None


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """The signed-in user, but only if they are staff.

    403 rather than 404: the caller is authenticated, they simply are not
    allowed. Hiding the route's existence buys nothing here -- it is in the
    OpenAPI schema either way.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return current_user
