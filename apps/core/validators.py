"""
Validadores de identificación ecuatoriana (cédula y RUC) y de archivos.

Reglas del SRI / Registro Civil:
- Cédula: 10 dígitos, provincia 01-24 o 30, tercer dígito < 6, dígito verificador módulo 10.
- RUC: 13 dígitos. Según el tercer dígito:
    0-5 → persona natural: los 10 primeros dígitos son una cédula válida; establecimiento (3 últimos) >= 001.
    6   → entidad pública: verificador módulo 11 en la posición 9; establecimiento (4 últimos) >= 0001.
    9   → sociedad privada: verificador módulo 11 en la posición 10; establecimiento (3 últimos) >= 001.

Algunas sociedades con RUC reciente no cumplen el módulo 11 (el SRI dejó de garantizarlo),
por eso para los tipos 6 y 9 el verificador no bloquea el registro: se marca y lo revisa el admin.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

VALID_PROVINCES = {f"{n:02d}" for n in range(1, 25)} | {"30"}


def _digits(value: str, length: int, label: str) -> str:
    value = (value or "").strip()
    if not value.isdigit() or len(value) != length:
        raise ValidationError(f"{label} debe tener {length} dígitos numéricos.", code="invalid_length")
    if value[:2] not in VALID_PROVINCES:
        raise ValidationError(f"{label}: código de provincia inválido.", code="invalid_province")
    return value


def _cedula_checksum_ok(value: str) -> bool:
    total = 0
    for i, coef in enumerate((2, 1, 2, 1, 2, 1, 2, 1, 2)):
        product = int(value[i]) * coef
        total += product - 9 if product > 9 else product
    return (10 - total % 10) % 10 == int(value[9])


def _mod11_ok(value: str, coefficients: tuple[int, ...], check_index: int) -> bool:
    total = sum(int(value[i]) * c for i, c in enumerate(coefficients))
    remainder = total % 11
    check = 0 if remainder == 0 else 11 - remainder
    return check != 10 and check == int(value[check_index])


def validate_cedula(value: str) -> str:
    value = _digits(value, 10, "La cédula")
    if int(value[2]) >= 6:
        raise ValidationError("La cédula no es válida (tercer dígito).", code="invalid_cedula")
    if not _cedula_checksum_ok(value):
        raise ValidationError("La cédula no es válida (dígito verificador).", code="invalid_cedula")
    return value


@dataclass(frozen=True)
class RucInfo:
    number: str
    taxpayer_type: str  # natural | public | private
    checksum_ok: bool


def validate_ruc(value: str) -> RucInfo:
    value = _digits(value, 13, "El RUC")
    third = int(value[2])

    if third < 6:
        if value[10:] == "000":
            raise ValidationError("El RUC no es válido (establecimiento 000).", code="invalid_ruc")
        if not _cedula_checksum_ok(value[:10]):
            raise ValidationError("El RUC no es válido (dígito verificador).", code="invalid_ruc")
        return RucInfo(value, "natural", True)

    if third == 6:
        if value[9:] == "0000":
            raise ValidationError("El RUC no es válido (establecimiento 0000).", code="invalid_ruc")
        return RucInfo(value, "public", _mod11_ok(value, (3, 2, 7, 6, 5, 4, 3, 2), 8))

    if third == 9:
        if value[10:] == "000":
            raise ValidationError("El RUC no es válido (establecimiento 000).", code="invalid_ruc")
        return RucInfo(value, "private", _mod11_ok(value, (4, 3, 2, 7, 6, 5, 4, 3, 2), 9))

    raise ValidationError("El RUC no es válido (tercer dígito).", code="invalid_ruc")


def validate_ruc_field(value: str) -> None:
    """Validador para campos de modelo/serializer."""
    validate_ruc(value)


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_image_file(file) -> None:
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"La imagen no puede superar {settings.MAX_IMAGE_SIZE_MB} MB.", code="file_too_large")
    content_type = getattr(file, "content_type", None)
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError("Formato de imagen no permitido (usa JPG, PNG o WEBP).", code="invalid_image_type")
