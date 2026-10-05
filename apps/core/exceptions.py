"""
Errores de dominio y formato uniforme de respuesta de error.

Toda respuesta de error de la API tiene la forma:
    {"detail": "mensaje legible", "code": "codigo_maquina", "errors": {...campo: [mensajes]}}
"""

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainError(exceptions.APIException):
    """Violación de una regla de negocio. Las vistas no necesitan capturarla."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No se pudo completar la operación."
    default_code = "domain_error"

    def __init__(self, detail=None, code=None, status_code=None, extra=None):
        super().__init__(detail, code)
        if status_code:
            self.status_code = status_code
        self.extra = extra or {}


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class TooSoonError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "too_soon"


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        )
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        errors = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        first = _first_message(errors)
        payload = {"detail": first or "Datos inválidos.", "code": "validation_error", "errors": errors}
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else response.data
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        payload = {"detail": str(detail), "code": code}
        if getattr(exc, "extra", None):
            payload.update(exc.extra)

    return Response(payload, status=response.status_code, headers=_retry_headers(response))


def _first_message(errors):
    if isinstance(errors, dict):
        for value in errors.values():
            found = _first_message(value)
            if found:
                return found
    elif isinstance(errors, list):
        for value in errors:
            found = _first_message(value)
            if found:
                return found
    elif errors:
        return str(errors)
    return None


def _retry_headers(response):
    retry = response.get("Retry-After") if hasattr(response, "get") else None
    return {"Retry-After": retry} if retry else None
