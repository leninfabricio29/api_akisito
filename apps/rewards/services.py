"""
Canje de recompensas.

Orden de bloqueo en todas las operaciones: Reward → Redemption → Membership.
Mantenerlo evita interbloqueos entre canjes, validaciones y expiraciones concurrentes.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.loyalty.models import Membership, PointTransaction
from apps.loyalty.services import apply_points, lock_membership
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .models import Redemption, Reward, generate_redemption_code

logger = logging.getLogger(__name__)
NOT_FOUND = "Código de canje no encontrado."


def redeem(client, reward_id: int) -> Redemption:
    with transaction.atomic():
        reward = get_object_or_404(
            Reward.objects.select_for_update(of=("self",)).select_related("business"), pk=reward_id
        )
        _ensure_available(reward)

        if reward.max_per_client is not None:
            used = Redemption.objects.filter(
                client=client, reward=reward, status__in=Redemption.ACTIVE_STATUSES
            ).count()
            if used >= reward.max_per_client:
                raise DomainError("Ya alcanzaste el máximo de canjes de esta recompensa.", code="redeem_limit")

        membership = lock_membership(client, reward.business)
        if membership.points_balance < reward.points_required:
            missing = reward.points_required - membership.points_balance
            raise DomainError(
                f"Te faltan {missing} pts en {reward.business.name} para esta recompensa.",
                code="insufficient_points",
                extra={"points_missing": missing},
            )

        redemption = _create_with_unique_code(
            client=client,
            reward=reward,
            business=reward.business,
            membership=membership,
            points_spent=reward.points_required,
            expires_at=timezone.now() + settings.REDEMPTION_CODE_TTL,
        )
        apply_points(
            membership, -reward.points_required, PointTransaction.Kind.REDEMPTION,
            f"Canje: {reward.title}", redemption=redemption,
        )
        Reward.objects.filter(pk=reward.pk).update(redeemed_count=F("redeemed_count") + 1)
    return redemption


def validate_code(business, code: str, by) -> Redemption:
    """El negocio valida el código que le muestra el cliente."""
    code = (code or "").strip().upper()
    expired = False
    with transaction.atomic():
        found = Redemption.objects.filter(code=code, business=business).values_list("reward_id", flat=True).first()
        if found is None:
            # Mismo mensaje exista o no en otro negocio: no se filtra información.
            raise DomainError(NOT_FOUND, code="redemption_not_found", status_code=404)

        Reward.objects.select_for_update().filter(pk=found).first()
        redemption = (
            Redemption.objects.select_for_update(of=("self",))
            .select_related("reward", "client")
            .get(code=code, business=business)
        )
        if redemption.status != Redemption.Status.PENDING:
            raise DomainError(
                f"Este código ya fue {redemption.get_status_display().lower()}.", code="redemption_not_pending"
            )
        if redemption.expires_at < timezone.now():
            _close_with_refund(redemption, Redemption.Status.EXPIRED, "Canje expirado")
            expired = True
        else:
            redemption.status = Redemption.Status.VALIDATED
            redemption.validated_at = timezone.now()
            redemption.validated_by = by
            redemption.closed_at = redemption.validated_at
            redemption.save(update_fields=["status", "validated_at", "validated_by", "closed_at", "updated_at"])
            Membership.objects.filter(pk=redemption.membership_id).update(
                redemptions_count=F("redemptions_count") + 1
            )
            notify(
                redemption.client,
                "¡Disfruta tu recompensa!",
                f"{business.name} validó tu canje: {redemption.reward.title}.",
                Notification.Kind.REDEMPTION,
                {"redemption_id": redemption.pk, "business_id": business.pk},
            )

    if expired:
        raise DomainError("El código expiró. Los puntos fueron devueltos al cliente.", code="redemption_expired")
    return redemption


def cancel(client, redemption_id: int) -> Redemption:
    with transaction.atomic():
        reward_id = get_object_or_404(Redemption, pk=redemption_id, client=client).reward_id
        Reward.objects.select_for_update().filter(pk=reward_id).first()
        redemption = Redemption.objects.select_for_update().get(pk=redemption_id)
        if redemption.status != Redemption.Status.PENDING:
            raise DomainError("Solo puedes cancelar canjes pendientes.", code="redemption_not_pending")
        _close_with_refund(redemption, Redemption.Status.CANCELLED, "Canje cancelado")
    return redemption


def expire_pending(now=None) -> int:
    """Expira los canjes vencidos y devuelve los puntos. Idempotente: seguro de ejecutar en paralelo."""
    now = now or timezone.now()
    due = Redemption.objects.filter(status=Redemption.Status.PENDING, expires_at__lt=now).values_list(
        "pk", "reward_id"
    )
    count = 0
    for pk, reward_id in list(due.iterator()):
        try:
            with transaction.atomic():
                Reward.objects.select_for_update().filter(pk=reward_id).first()
                redemption = Redemption.objects.select_for_update(skip_locked=True).filter(
                    pk=pk, status=Redemption.Status.PENDING
                ).first()
                if redemption is None:
                    continue
                _close_with_refund(redemption, Redemption.Status.EXPIRED, "Canje expirado")
                notify(
                    redemption.client_id,
                    "Tu canje expiró",
                    f"Devolvimos {redemption.points_spent} pts a tu monedero.",
                    Notification.Kind.REDEMPTION,
                    {"redemption_id": redemption.pk},
                    send_push=False,
                )
                count += 1
        except Exception:  # noqa: BLE001 - un canje con error no debe frenar el resto
            logger.exception("No se pudo expirar el canje %s", pk)
    return count


def _close_with_refund(redemption: Redemption, new_status: str, label: str) -> None:
    membership = Membership.objects.select_for_update(of=("self",)).select_related("business").get(
        pk=redemption.membership_id
    )
    apply_points(
        membership, redemption.points_spent, PointTransaction.Kind.REFUND,
        f"{label}: {redemption.code}", redemption=redemption,
    )
    redemption.status = new_status
    redemption.closed_at = timezone.now()
    redemption.save(update_fields=["status", "closed_at", "updated_at"])
    Reward.objects.filter(pk=redemption.reward_id, redeemed_count__gt=0).update(
        redeemed_count=F("redeemed_count") - 1
    )


def _ensure_available(reward: Reward) -> None:
    now = timezone.now()
    if not reward.business.is_approved:
        raise DomainError("Este negocio no está disponible.", code="business_unavailable")
    if not reward.is_active or reward.starts_at > now or (reward.ends_at and reward.ends_at < now):
        raise DomainError("Esta recompensa no está disponible.", code="reward_unavailable")
    if reward.stock is not None and reward.redeemed_count >= reward.stock:
        raise DomainError("Esta recompensa se agotó.", code="reward_sold_out")


def _create_with_unique_code(**fields) -> Redemption:
    for _ in range(5):
        try:
            with transaction.atomic():
                return Redemption.objects.create(code=generate_redemption_code(), **fields)
        except IntegrityError:
            continue
    raise DomainError("No se pudo generar el código, inténtalo de nuevo.", status_code=503)


def notify_new_reward(reward: Reward) -> int:
    """Avisa a los clientes del negocio (miembros y favoritos). Push en cola."""
    from apps.businesses.models import Favorite

    members = set(Membership.objects.filter(business=reward.business).values_list("client_id", flat=True))
    fans = set(Favorite.objects.filter(business=reward.business).values_list("client_id", flat=True))
    return notify(
        members | fans,
        f"Nueva recompensa en {reward.business.name}",
        f"{reward.title} por {reward.points_required} pts.",
        Notification.Kind.REWARD,
        {"reward_id": reward.pk, "business_id": reward.business_id},
    )
