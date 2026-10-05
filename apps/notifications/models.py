from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Device(TimeStampedModel):
    """Token FCM de un teléfono. Un token pertenece al último usuario que inició sesión en ese equipo."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices", verbose_name="usuario"
    )
    token = models.CharField("token FCM", max_length=255, unique=True)
    platform = models.CharField("plataforma", max_length=10, choices=Platform.choices, blank=True)
    name = models.CharField("nombre", max_length=120, blank=True)
    is_active = models.BooleanField("activo", default=True)
    last_seen_at = models.DateTimeField("última actividad", auto_now=True)

    class Meta:
        verbose_name = "dispositivo"
        verbose_name_plural = "dispositivos"
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.user} · {self.name or self.platform or 'dispositivo'}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        POINTS = "points", "Puntos"
        REWARD = "reward", "Recompensa"
        REDEMPTION = "redemption", "Canje"
        REVIEW = "review", "Reseña"
        WINBACK = "winback", "Te extrañamos"
        BUSINESS = "business", "Estado del negocio"
        NEW_BUSINESS = "new_business", "Nuevo negocio"
        SYSTEM = "system", "Sistema"

    class PushStatus(models.TextChoices):
        NONE = "none", "Sin push"
        PENDING = "pending", "Pendiente"
        SENT = "sent", "Enviada"
        FAILED = "failed", "Fallida"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", verbose_name="usuario"
    )
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices, db_index=True)
    title = models.CharField("título", max_length=120)
    body = models.CharField("mensaje", max_length=500)
    data = models.JSONField("datos", default=dict, blank=True, help_text="Datos para navegación en la app.")
    read_at = models.DateTimeField("leída", null=True, blank=True)
    push_status = models.CharField(
        "push", max_length=8, choices=PushStatus.choices, default=PushStatus.NONE, db_index=True
    )
    pushed_at = models.DateTimeField("push enviado", null=True, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return f"{self.title} → {self.user}"
