import io

import qrcode
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.emails import send_template_email_on_commit
from apps.core.exceptions import ConflictError, DomainError
from apps.core.validators import validate_ruc

from .models import QR_SCHEME, Business


@transaction.atomic
def create_business(owner: User, data: dict) -> Business:
    """Crea el negocio del propietario en estado pendiente de aprobación (un negocio por cuenta)."""
    User.objects.select_for_update().filter(pk=owner.pk).first()
    if Business.objects.filter(owner=owner).exists():
        raise ConflictError("Tu cuenta ya tiene un negocio registrado.")
    ruc_info = validate_ruc(data["ruc"])
    created = Business.objects.create(
        owner=owner,
        taxpayer_type=ruc_info.taxpayer_type,
        ruc_checksum_ok=ruc_info.checksum_ok,
        **{**data, "ruc": ruc_info.number},
    )
    send_template_email_on_commit(
        owner.email,
        "business_submitted",
        {"name": owner.get_full_name(), "business_name": created.name},
    )
    return created


STATUS_MESSAGES = {
    Business.Status.APPROVED: ("¡Tu negocio fue aprobado!", "Ya puedes imprimir tu QR y crear recompensas."),
    Business.Status.REJECTED: ("Tu negocio no fue aprobado", "Revisa el motivo y actualiza tus datos."),
    Business.Status.SUSPENDED: ("Tu negocio fue suspendido", "Contacta a soporte para más información."),
}


@transaction.atomic
def set_status(business: Business, new_status: str, *, reason: str = "", by=None) -> Business:
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    if new_status == Business.Status.APPROVED and business.latitude is None:
        raise DomainError("El negocio no tiene ubicación registrada.")
    if new_status in (Business.Status.REJECTED, Business.Status.SUSPENDED) and not reason:
        raise DomainError("Debes indicar el motivo.")

    business.status = new_status
    business.status_reason = reason
    business.reviewed_at = timezone.now()
    business.reviewed_by = by
    business.save(update_fields=["status", "status_reason", "reviewed_at", "reviewed_by", "updated_at"])

    if new_status == Business.Status.APPROVED and business.announced_at is None:
        announce_new_business(business)

    title, body = STATUS_MESSAGES.get(new_status, ("Estado de tu negocio actualizado", ""))
    notify(business.owner, title, reason or body, Notification.Kind.BUSINESS, {"business_id": business.pk})
    send_template_email_on_commit(
        business.owner.email,
        "business_status",
        {
            "name": business.owner.get_full_name(),
            "business_name": business.name,
            "approved": new_status == Business.Status.APPROVED,
            "status_label": business.get_status_display(),
            "reason": reason,
        },
    )
    return business


def announce_new_business(business: Business) -> int:
    """
    Avisa a todos los clientes activos que hay un nuevo negocio aliado (nunca a otros negocios).
    Solo en la primera aprobación: `announced_at` evita repetirlo tras una suspensión.
    """
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    business.announced_at = timezone.now()
    business.save(update_fields=["announced_at", "updated_at"])
    clients = User.objects.filter(role=User.Role.CLIENT, is_active=True).values_list("pk", flat=True)
    return notify(
        list(clients),
        "¡Nuevo negocio en Akisito! 🎉",
        f"{business.name} ya es aliado. Visítalo, escanea su QR y gana puntos.",
        Notification.Kind.NEW_BUSINESS,
        {"business_id": business.pk},
    )


def resubmit(business: Business) -> Business:
    if business.status != Business.Status.REJECTED:
        raise DomainError("Solo puedes reenviar un negocio rechazado.")
    business.status = Business.Status.PENDING
    business.status_reason = ""
    business.save(update_fields=["status", "status_reason", "updated_at"])
    return business


def parse_qr_token(raw: str) -> str:
    """Acepta el contenido completo del QR (akisito://checkin/<token>) o solo el token."""
    raw = (raw or "").strip()
    if raw.startswith(QR_SCHEME):
        raw = raw[len(QR_SCHEME):]
    return raw.split("?")[0].strip("/")


def qr_png(business: Business, box_size: int = 12) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=3)
    qr.add_data(business.qr_payload)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()
