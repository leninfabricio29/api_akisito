"""
Movimiento de puntos. Única puerta de entrada para cambiar saldos.

Toda función que modifica saldo exige estar dentro de `transaction.atomic()` y trabaja
sobre una membresía bloqueada con `select_for_update`, así dos peticiones simultáneas
(p. ej. dos canjes) nunca pueden gastar los mismos puntos.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError

from .models import LoyaltySettings, Membership, PointTransaction

EARNING_KINDS = {PointTransaction.Kind.CHECKIN, PointTransaction.Kind.REVIEW, PointTransaction.Kind.ADJUSTMENT}


def get_settings() -> LoyaltySettings:
    return LoyaltySettings.load()


def checkin_points_for(business, cfg: LoyaltySettings | None = None) -> int:
    cfg = cfg or get_settings()
    return business.checkin_points or cfg.checkin_points


def review_points_for(business, cfg: LoyaltySettings | None = None) -> int:
    cfg = cfg or get_settings()
    return business.review_points if business.review_points is not None else cfg.review_points


def checkin_radius_for(business, cfg: LoyaltySettings | None = None) -> int:
    cfg = cfg or get_settings()
    return business.checkin_radius_m or cfg.checkin_radius_m


def lock_membership(client, business) -> Membership:
    """Obtiene (o crea) la membresía y la bloquea hasta el fin de la transacción."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("lock_membership debe llamarse dentro de transaction.atomic()")
    Membership.objects.get_or_create(client=client, business=business)
    return Membership.objects.select_for_update(of=("self",)).select_related("business").get(client=client, business=business)


def apply_points(
    membership: Membership,
    points: int,
    kind: str,
    description: str,
    *,
    checkin=None,
    review=None,
    redemption=None,
    created_by=None,
) -> PointTransaction:
    """Suma o resta puntos a una membresía YA bloqueada y registra el movimiento."""
    if points == 0:
        raise ValueError("Un movimiento de puntos no puede ser 0.")

    new_balance = membership.points_balance + points
    if new_balance < 0:
        raise DomainError(
            f"Saldo insuficiente en {membership.business.name}: tienes {membership.points_balance} pts.",
            code="insufficient_points",
        )

    now = timezone.now()
    membership.points_balance = new_balance
    membership.last_activity_at = now
    update_fields = ["points_balance", "last_activity_at", "updated_at"]
    if points > 0 and kind in EARNING_KINDS:
        membership.lifetime_points += points
        update_fields.append("lifetime_points")
    membership.save(update_fields=update_fields)

    return PointTransaction.objects.create(
        membership=membership,
        kind=kind,
        points=points,
        balance_after=new_balance,
        description=description[:255],
        checkin=checkin,
        review=review,
        redemption=redemption,
        created_by=created_by,
    )


@transaction.atomic
def adjust_points(membership_id: int, points: int, description: str, by) -> PointTransaction:
    """Ajuste manual desde el admin (compensaciones, correcciones)."""
    membership = Membership.objects.select_for_update(of=("self",)).select_related("business").get(pk=membership_id)
    return apply_points(membership, points, PointTransaction.Kind.ADJUSTMENT, description, created_by=by)


def expire_inactive_points(now=None) -> int:
    """Vence el saldo de membresías sin actividad durante el periodo configurado. Devuelve cuántas venció."""
    cfg = get_settings()
    if not cfg.points_expiration_enabled:
        return 0

    now = now or timezone.now()
    limit = now - timedelta(days=cfg.points_expire_after_days)
    candidates = Membership.objects.filter(points_balance__gt=0, last_activity_at__lt=limit).values_list("pk", flat=True)

    expired = 0
    for pk in candidates.iterator():
        with transaction.atomic():
            membership = Membership.objects.select_for_update(of=("self",)).select_related("business").get(pk=pk)
            if membership.points_balance == 0 or (membership.last_activity_at and membership.last_activity_at >= limit):
                continue
            apply_points(
                membership,
                -membership.points_balance,
                PointTransaction.Kind.EXPIRATION,
                f"Vencimiento por {cfg.points_expire_after_days} días sin actividad",
            )
            expired += 1
    return expired
