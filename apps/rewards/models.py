import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_file

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I para dictarlo sin errores
CODE_LENGTH = 8


def generate_redemption_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class RewardQuerySet(models.QuerySet):
    def available(self, now=None):
        now = now or timezone.now()
        return (
            self.filter(is_active=True, starts_at__lte=now, business__status="approved", business__owner__is_active=True)
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            .filter(models.Q(stock__isnull=True) | models.Q(redeemed_count__lt=models.F("stock")))
        )


class Reward(TimeStampedModel):
    """Recompensa que un negocio ofrece a cambio de sus propios puntos."""

    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="rewards", verbose_name="negocio"
    )
    title = models.CharField("título", max_length=120)
    description = models.TextField("descripción", blank=True)
    image = models.ImageField("imagen", upload_to="rewards/", blank=True, validators=[validate_image_file])
    points_required = models.PositiveIntegerField("puntos requeridos", validators=[MinValueValidator(1)])
    starts_at = models.DateTimeField("disponible desde", default=timezone.now)
    ends_at = models.DateTimeField("disponible hasta", null=True, blank=True)
    max_per_client = models.PositiveSmallIntegerField(
        "canjes máximos por cliente", null=True, blank=True, default=1,
        help_text="Vacío = sin límite por cliente.",
    )
    stock = models.PositiveIntegerField("stock total", null=True, blank=True, help_text="Vacío = sin límite.")
    redeemed_count = models.PositiveIntegerField("canjes reservados", default=0)
    is_active = models.BooleanField("activa", default=True)

    objects = RewardQuerySet.as_manager()

    class Meta:
        verbose_name = "recompensa"
        verbose_name_plural = "recompensas"
        ordering = ["points_required", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.points_required} pts) · {self.business.name}"

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "La fecha de fin debe ser posterior a la de inicio."})
        if self.stock is not None and self.pk and self.stock < self.redeemed_count:
            raise ValidationError({"stock": f"Ya hay {self.redeemed_count} canjes; el stock no puede ser menor."})

    @property
    def stock_left(self):
        return None if self.stock is None else max(self.stock - self.redeemed_count, 0)


class Redemption(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de validar"
        VALIDATED = "validated", "Validado"
        EXPIRED = "expired", "Expirado (puntos devueltos)"
        CANCELLED = "cancelled", "Cancelado (puntos devueltos)"

    ACTIVE_STATUSES = (Status.PENDING, Status.VALIDATED)

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="redemptions", verbose_name="cliente"
    )
    # La API no borra recompensas con canjes (las desactiva); con CASCADE el superusuario puede borrarlas desde el admin.
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE, related_name="redemptions", verbose_name="recompensa")
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="redemptions", verbose_name="negocio"
    )
    membership = models.ForeignKey("loyalty.Membership", on_delete=models.CASCADE, related_name="redemptions")
    points_spent = models.PositiveIntegerField("puntos usados")
    code = models.CharField("código", max_length=CODE_LENGTH, unique=True)
    status = models.CharField(
        "estado", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    expires_at = models.DateTimeField("expira", db_index=True)
    validated_at = models.DateTimeField("validado", null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="validado por",
    )
    closed_at = models.DateTimeField("cerrado", null=True, blank=True)

    class Meta:
        verbose_name = "canje"
        verbose_name_plural = "canjes"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["client", "reward", "status"])]

    def __str__(self):
        return f"{self.code} · {self.reward.title} ({self.get_status_display()})"
