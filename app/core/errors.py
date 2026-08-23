"""Domain-level exceptions, translated to HTTP once, in the router layer."""
from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, user-facing failures."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class PermissionDeniedError(DomainError):
    status_code = 403


class AuthenticationError(DomainError):
    status_code = 401


class ValidationError(DomainError):
    status_code = 422
