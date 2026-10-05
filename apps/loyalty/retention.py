"""Campañas automáticas de retención."""

from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import notify

from .models import Membership
from .services import get_settings


def send_winback(now=None) -> int:
    """
    Recuerda a los clientes que dejaron de visitar un negocio hace `winback_days` días.
    Se envía una sola vez por periodo de inactividad (se reinicia cuando el cliente vuelve).
    """
    cfg = get_settings()
    if not cfg.winback_enabled:
        return 0

    now = now or timezone.now()
    limit = now - timedelta(days=cfg.winback_days)
    due = (
        Membership.objects.filter(
            last_checkin_at__lt=limit,
            client__is_active=True,
            business__status="approved",
        )
        .filter(Q(winback_sent_at__isnull=True) | Q(winback_sent_at__lt=F("last_checkin_at")))
        .select_related("business")
    )

    sent = 0
    for membership in due.iterator(chunk_size=500):
        extra = f" Tienes {membership.points_balance} pts esperándote." if membership.points_balance else ""
        notify(
            membership.client_id,
            f"¡Te extrañamos en {membership.business.name}!",
            f"Vuelve y suma puntos en tu próxima visita.{extra}",
            Notification.Kind.WINBACK,
            {"business_id": membership.business_id},
        )
        Membership.objects.filter(pk=membership.pk).update(winback_sent_at=now)
        sent += 1
    return sent
