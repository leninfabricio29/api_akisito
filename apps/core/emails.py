"""Envío de correos con plantillas HTML (templates/emails/*.html)."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

SUBJECTS = {
    "signup_code": "✉️ Tu código para crear tu cuenta — Akisito",
    "business_submitted": "📋 Recibimos los datos de tu negocio — Akisito",
    "password_reset_code": "🔐 Tu código de recuperación — Akisito",
    "account_created": "✅ ¡Tu cuenta fue creada! — Akisito",
    "password_changed": "🔑 Tu contraseña fue actualizada — Akisito",
    "business_status": "📋 Estado de tu negocio — Akisito",
}


def send_template_email(to: str, template: str, context: dict, subject: str | None = None) -> bool:
    """Envía el correo y devuelve True si salió. Nunca lanza excepción."""
    html = render_to_string(f"emails/{template}.html", context)
    message = EmailMultiAlternatives(
        subject=subject or SUBJECTS.get(template, "Akisito"),
        body=strip_tags(html),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
    )
    message.attach_alternative(html, "text/html")
    try:
        message.send()
        return True
    except Exception:  # noqa: BLE001 - un SMTP caído no debe romper la operación del usuario
        logger.exception("No se pudo enviar el correo '%s' a %s", template, to)
        return False


def send_template_email_on_commit(to: str, template: str, context: dict, subject: str | None = None) -> None:
    """Envía el correo solo si la transacción actual se confirma."""
    transaction.on_commit(lambda: send_template_email(to, template, context, subject))
