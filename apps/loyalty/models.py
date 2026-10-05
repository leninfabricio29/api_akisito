from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import SingletonModel, TimeStampedModel


class LoyaltySettings(SingletonModel):
    """Reglas globales del programa. Cada negocio puede sobrescribir puntos y radio."""

    checkin_points = models.PositiveSmallIntegerField("puntos por visita", default=10, validators=[MinValueValidator(1)])
    review_points = models.PositiveSmallIntegerField("puntos por reseña", default=10)
    checkin_cooldown_hours = models.PositiveSmallIntegerField(
        "horas entre visitas con puntos", default=4, validators=[MinValueValidator(1)],
        help_text="Tiempo mínimo entre dos check-ins del mismo cliente en el mismo negocio.",
    )
    max_checkins_per_day = models.PositiveSmallIntegerField(
        "máximo de check-ins por día (por cliente)", default=10, validators=[MinValueValidator(1)],
        help_text="Límite anti-fraude sumando todos los negocios.",
    )
    checkin_radius_m = models.PositiveSmallIntegerField("radio de check-in por defecto (m)", default=150)
    max_gps_accuracy_m = models.PositiveSmallIntegerField(
        "precisión GPS mínima aceptada (m)", default=100,
        help_text="Se rechaza el check-in si el GPS reporta una precisión peor que este valor.",
    )
    review_window_hours = models.PositiveSmallIntegerField(
        "horas para reseñar tras la visita", default=48, validators=[MinValueValidator(1)]
    )
    review_points_cooldown_days = models.PositiveSmallIntegerField(
        "días entre reseñas con puntos (por negocio)", default=30,
        help_text="El cliente puede reseñar cada visita, pero solo gana puntos una vez en este periodo.",
    )
    winback_enabled = models.BooleanField("recordatorio a clientes inactivos", default=True)
    winback_days = models.PositiveSmallIntegerField("días de inactividad para recordatorio", default=30)
    points_expiration_enabled = models.BooleanField("vencimiento de puntos", default=False)
    points_expire_after_days = models.PositiveSmallIntegerField(
        "días sin actividad para vencer puntos", default=365, validators=[MinValueValidator(30)]
    )

    class Meta:
        verbose_name = "configuración de puntos"
        verbose_name_plural = "configuración de puntos"

    def __str__(self):
        return "Configuración del programa de puntos"


class Membership(TimeStampedModel):
    """Relación cliente-negocio: el monedero de puntos del cliente en ese local."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships", verbose_name="cliente"
    )
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="memberships", verbose_name="negocio"
    )
    points_balance = models.PositiveIntegerField("saldo", default=0)
    lifetime_points = models.PositiveIntegerField("puntos ganados (histórico)", default=0)
    checkins_count = models.PositiveIntegerField("visitas", default=0)
    reviews_count = models.PositiveIntegerField("reseñas", default=0)
    redemptions_count = models.PositiveIntegerField("canjes", default=0)
    first_checkin_at = models.DateTimeField("primera visita", null=True, blank=True)
    last_checkin_at = models.DateTimeField("última visita", null=True, blank=True, db_index=True)
    last_activity_at = models.DateTimeField("última actividad", null=True, blank=True)
    winback_sent_at = models.DateTimeField("recordatorio enviado", null=True, blank=True)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        ordering = ["-last_checkin_at"]
        constraints = [
            models.UniqueConstraint(fields=["client", "business"], name="unique_membership"),
            models.CheckConstraint(condition=models.Q(points_balance__gte=0), name="membership_balance_non_negative"),
        ]

    def __str__(self):
        return f"{self.client} @ {self.business.name}: {self.points_balance} pts"


class PointTransaction(models.Model):
    """Libro contable de puntos. Nunca se edita ni se borra: se compensa con otro movimiento."""

    class Kind(models.TextChoices):
        CHECKIN = "checkin", "Visita"
        REVIEW = "review", "Reseña"
        REDEMPTION = "redemption", "Canje"
        REFUND = "refund", "Devolución de canje"
        ADJUSTMENT = "adjustment", "Ajuste manual"
        EXPIRATION = "expiration", "Vencimiento"

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices, db_index=True)
    points = models.IntegerField("puntos")
    balance_after = models.PositiveIntegerField("saldo resultante")
    description = models.CharField("descripción", max_length=255)
    checkin = models.ForeignKey("checkins.CheckIn", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    review = models.ForeignKey("reviews.Review", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    redemption = models.ForeignKey(
        "rewards.Redemption", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="registrado por",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "movimiento de puntos"
        verbose_name_plural = "movimientos de puntos"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        sign = "+" if self.points >= 0 else ""
        return f"{sign}{self.points} · {self.get_kind_display()}"
