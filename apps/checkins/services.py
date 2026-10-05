"""
Check-in por QR: el cliente escanea el QR del negocio y, en una sola llamada,
se valida su ubicación y se otorgan los puntos.

Orden de validación:
  1. QR válido y negocio aprobado.
  2. Ubicación: no simulada, precisión GPS aceptable y dentro del radio del negocio.
  3. Límite diario del cliente (todos los negocios).
  4. Tiempo mínimo entre visitas al mismo negocio.

Los intentos rechazados por ubicación o límites se guardan (status=rejected) para
que el admin pueda detectar patrones de fraude.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.businesses.services import parse_qr_token
from apps.core.exceptions import DomainError, TooSoonError
from apps.core.geo import haversine_m
from apps.loyalty.models import PointTransaction
from apps.loyalty.services import (
    apply_points,
    checkin_points_for,
    checkin_radius_for,
    get_settings,
    lock_membership,
    review_points_for,
)
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .models import CheckIn

Reason = CheckIn.RejectReason

REJECT_MESSAGES = {
    Reason.MOCKED_LOCATION: "Detectamos una ubicación simulada. Desactívala para registrar tu visita.",
    Reason.LOW_ACCURACY: "Tu GPS no tiene suficiente precisión. Activa la ubicación precisa e inténtalo de nuevo.",
    Reason.OUT_OF_RANGE: "Debes estar en {business} para registrar tu visita (estás a {distance} m).",
    Reason.DAILY_LIMIT: "Alcanzaste el máximo de visitas por hoy. ¡Vuelve mañana!",
    Reason.COOLDOWN: "Ya registraste tu visita en {business}. Podrás sumar puntos de nuevo desde las {next_at}.",
}


@dataclass
class ScanResult:
    checkin: CheckIn
    membership: object
    review_points: int


def scan(client: User, *, qr: str, latitude, longitude, accuracy_m=None, is_mocked=False) -> ScanResult:
    token = parse_qr_token(qr)
    business = Business.objects.select_related("owner").filter(qr_token=token).first() if token else None
    if business is None:
        raise DomainError("Este código QR no pertenece a ningún negocio de Akisito.", code="invalid_qr",
                          status_code=status.HTTP_404_NOT_FOUND)
    if not business.is_approved or not business.owner.is_active:
        raise DomainError("Este negocio no está disponible por el momento.", code="business_unavailable")

    cfg = get_settings()
    now = timezone.now()
    distance = haversine_m(latitude, longitude, business.latitude, business.longitude)
    radius = checkin_radius_for(business, cfg)

    base = {
        "client": client,
        "business": business,
        "latitude": Decimal(str(round(float(latitude), 6))),
        "longitude": Decimal(str(round(float(longitude), 6))),
        "accuracy_m": int(accuracy_m) if accuracy_m is not None else None,
        "distance_m": int(distance),
        "is_mocked": bool(is_mocked),
    }

    reason, context = None, {}
    with transaction.atomic():
        # Bloquear al cliente serializa sus check-ins: el límite diario no se puede saltar con peticiones paralelas.
        User.objects.select_for_update().filter(pk=client.pk).first()

        if is_mocked:
            reason = Reason.MOCKED_LOCATION
        elif accuracy_m is not None and accuracy_m > cfg.max_gps_accuracy_m:
            reason = Reason.LOW_ACCURACY
        elif distance > radius:
            reason = Reason.OUT_OF_RANGE
        elif _awarded_today(client, now) >= cfg.max_checkins_per_day:
            reason = Reason.DAILY_LIMIT

        if reason is None:
            membership = lock_membership(client, business)
            cooldown = timedelta(hours=cfg.checkin_cooldown_hours)
            if membership.last_checkin_at and now < membership.last_checkin_at + cooldown:
                reason = Reason.COOLDOWN
                context["next_at"] = membership.last_checkin_at + cooldown

        if reason is not None:
            CheckIn.objects.create(**base, status=CheckIn.Status.REJECTED, reject_reason=reason)
        else:
            result = _award(business, membership, base, cfg, now)

    if reason is not None:
        _raise_rejection(reason, business, distance, context)
    return result


def _award(business, membership, base, cfg, now) -> ScanResult:
    points = checkin_points_for(business, cfg)
    checkin = CheckIn.objects.create(
        **base,
        status=CheckIn.Status.AWARDED,
        points_awarded=points,
        review_deadline=now + timedelta(hours=cfg.review_window_hours),
    )
    apply_points(membership, points, PointTransaction.Kind.CHECKIN, f"Visita a {business.name}", checkin=checkin)

    membership.checkins_count += 1
    membership.first_checkin_at = membership.first_checkin_at or now
    membership.last_checkin_at = now
    membership.save(update_fields=["checkins_count", "first_checkin_at", "last_checkin_at", "updated_at"])

    review_points = pending_review_points(membership.client, business, cfg, now)
    notify(
        membership.client,
        f"+{points} pts en {business.name}",
        f"Tu saldo en {business.name} es {membership.points_balance} pts."
        + (f" Deja una reseña y gana {review_points} pts más." if review_points else ""),
        Notification.Kind.POINTS,
        {"business_id": business.pk, "checkin_id": checkin.pk},
        send_push=False,  # el cliente ya está viendo el resultado en pantalla
    )
    return ScanResult(checkin=checkin, membership=membership, review_points=review_points)


def pending_review_points(client, business, cfg=None, now=None) -> int:
    """Puntos que ganaría una reseña ahora (0 si ya ganó puntos por reseña en el periodo)."""
    from apps.reviews.models import Review

    cfg = cfg or get_settings()
    now = now or timezone.now()
    points = review_points_for(business, cfg)
    if not points:
        return 0
    since = now - timedelta(days=cfg.review_points_cooldown_days)
    already = Review.objects.filter(
        client=client, business=business, points_awarded__gt=0, created_at__gte=since
    ).exists()
    return 0 if already else points


def _awarded_today(client, now) -> int:
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return CheckIn.objects.filter(client=client, status=CheckIn.Status.AWARDED, created_at__gte=start).count()


def _raise_rejection(reason, business, distance, context):
    extra = {"reason": reason}
    message = REJECT_MESSAGES[reason]
    if reason == Reason.COOLDOWN:
        next_at = context["next_at"]
        extra["next_checkin_at"] = next_at.isoformat()
        message = message.format(business=business.name, next_at=timezone.localtime(next_at).strftime("%H:%M"))
        raise TooSoonError(message, code="checkin_cooldown", extra=extra)
    if reason == Reason.DAILY_LIMIT:
        raise TooSoonError(message, code="checkin_daily_limit", extra=extra)
    if reason == Reason.OUT_OF_RANGE:
        extra["distance_m"] = int(distance)
        message = message.format(business=business.name, distance=int(distance))
    raise DomainError(message, code=f"checkin_{reason}", extra=extra)
