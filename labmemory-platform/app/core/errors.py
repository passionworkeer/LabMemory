"""领域异常。"""
from __future__ import annotations


class DomainError(Exception):
    code: str = "domain_error"
    status_code: int = 400

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    status_code = 403


class ValidationFailedError(DomainError):
    code = "validation_failed"
    status_code = 422


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409


class StateTransitionError(DomainError):
    code = "invalid_state"
    status_code = 409
