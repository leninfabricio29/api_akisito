"""
Notificaciones en la app + push.

- `notify()` guarda las notificaciones y, si son pocas, envía el push al confirmar la transacción.
- Los envíos masivos (p. ej. una nueva recompensa para todos los miembros) quedan en estado
  `pending` y los despacha el command `dispatch_notifications` (programado cada minuto).
"""

import logging
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from . import push
from .models import Device, Notification

logger = logging.getLogger(__name__)

IMMEDIATE_PUSH_LIMIT = 5


def notify(users, title: str, body: str, kind: str, data: dict | None = None, send_push: bool = True) -> int:
    """Crea una notificación por usuario. `users` puede ser un usuario, un id o un iterable de ellos."""
    user_ids = _to_ids(users)
    if not user_ids:
        return 0

    status = Notification.PushStatus.PENDING if send_push else Notification.PushStatus.NONE
    created = Notification.objects.bulk_create(
        [
            Notification(user_id=uid, kind=kind, title=title[:120], body=body[:500], data=data or {}, push_status=status)
            for uid in user_ids
        ],
        batch_size=1000,
    )

    if send_push and len(created) <= IMMEDIATE_PUSH_LIMIT:
        ids = [n.pk for n in created]
        transaction.on_commit(lambda: _safe_dispatch(ids))
    return len(created)


def dispatch_pending(limit: int = 2000) -> int:
    """Envía los push pendientes. Agrupa por mensaje idéntico para usar multicast."""
    pending = list(
        Notification.objects.filter(push_status=Notification.PushStatus.PENDING).order_by("created_at")[:limit]
    )
    return _dispatch(pending)


def _safe_dispatch(ids: list[int]) -> None:
    try:
        _dispatch(list(Notification.objects.filter(pk__in=ids, push_status=Notification.PushStatus.PENDING)))
    except Exception:  # noqa: BLE001 - quedan pendientes para el command
        logger.exception("Push inmediato falló; se reintentará con dispatch_notifications")


def _dispatch(notifications: list[Notification]) -> int:
    if not notifications:
        return 0

    if not push.is_enabled():
        Notification.objects.filter(pk__in=[n.pk for n in notifications]).update(
            push_status=Notification.PushStatus.FAILED
        )
        logger.warning("Firebase no configurado: %s push marcados como fallidos", len(notifications))
        return 0

    groups: dict[tuple, list[Notification]] = {}
    for n in notifications:
        key = (n.title, n.body, n.kind, tuple(sorted((k, str(v)) for k, v in (n.data or {}).items())))
        groups.setdefault(key, []).append(n)

    total_sent = 0
    for (title, body, kind, data_items), items in groups.items():
        user_ids = {n.user_id for n in items}
        tokens = list(Device.objects.filter(user_id__in=user_ids, is_active=True).values_list("token", flat=True))
        ids = [n.pk for n in items]

        if not tokens:
            Notification.objects.filter(pk__in=ids).update(push_status=Notification.PushStatus.NONE)
            continue

        try:
            sent, invalid = push.send_to_tokens(tokens, title, body, {"kind": kind, **dict(data_items)})
        except Exception:  # noqa: BLE001
            continue  # siguen pendientes

        if invalid:
            Device.objects.filter(token__in=invalid).update(is_active=False)
        Notification.objects.filter(pk__in=ids).update(
            push_status=Notification.PushStatus.SENT if sent else Notification.PushStatus.FAILED,
            pushed_at=timezone.now(),
        )
        total_sent += sent
    return total_sent


def register_device(user, token: str, platform: str = "", name: str = "") -> Device:
    """El token se reasigna al usuario actual si el teléfono cambió de cuenta."""
    device, _ = Device.objects.update_or_create(
        token=token, defaults={"user": user, "platform": platform, "name": name, "is_active": True}
    )
    return device


def unregister_device(user, token: str) -> None:
    Device.objects.filter(user=user, token=token).update(is_active=False)


def _to_ids(users) -> list[int]:
    if users is None:
        return []
    if isinstance(users, int):
        return [users]
    if hasattr(users, "pk"):
        return [users.pk]
    if isinstance(users, Iterable):
        return list(dict.fromkeys(u if isinstance(u, int) else u.pk for u in users))
    return []
