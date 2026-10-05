"""Envío de notificaciones push con Firebase Cloud Messaging."""

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_app = None
_lock = threading.Lock()
FCM_BATCH = 500


def _get_app():
    global _app
    if _app is not None:
        return _app
    if not settings.FIREBASE_CREDENTIALS:
        return None
    with _lock:
        if _app is None:
            import firebase_admin
            from firebase_admin import credentials

            try:
                _app = firebase_admin.get_app()
            except ValueError:
                _app = firebase_admin.initialize_app(credentials.Certificate(settings.FIREBASE_CREDENTIALS))
    return _app


def is_enabled() -> bool:
    return _get_app() is not None


def send_to_tokens(tokens: list[str], title: str, body: str, data: dict | None = None) -> tuple[int, list[str]]:
    """
    Envía el mensaje a los tokens. Devuelve (enviados, tokens_invalidos).
    Los tokens inválidos deben desactivarse por quien llama.
    """
    app = _get_app()
    if app is None or not tokens:
        return 0, []

    from firebase_admin import messaging

    payload = {k: str(v) for k, v in (data or {}).items()}
    sent, invalid = 0, []

    for start in range(0, len(tokens), FCM_BATCH):
        chunk = tokens[start:start + FCM_BATCH]
        message = messaging.MulticastMessage(
            tokens=chunk,
            notification=messaging.Notification(title=title, body=body),
            data=payload,
            android=messaging.AndroidConfig(
                priority="high", notification=messaging.AndroidNotification(sound="default", channel_id="default")
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"}, payload=messaging.APNSPayload(aps=messaging.Aps(sound="default"))
            ),
        )
        try:
            response = messaging.send_each_for_multicast(message, app=app)
        except Exception:  # noqa: BLE001 - FCM puede fallar por red; se reintenta en el próximo dispatch
            logger.exception("Error enviando push a %s dispositivos", len(chunk))
            raise

        sent += response.success_count
        for token, result in zip(chunk, response.responses):
            if not result.success and isinstance(
                result.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError)
            ):
                invalid.append(token)
    return sent, invalid
