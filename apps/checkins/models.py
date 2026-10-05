from datetime import timedelta

from django.conf import settings
from django.db import models


class CheckIn(models.Model):
    """Cada escaneo del QR de un negocio. Los rechazados se guardan para detectar fraude."""

    class Status(models.TextChoices):
        AWARDED = "awarded", "Puntos otorgados"
        REJECTED = "rejected", "Rechazado"

    class RejectReason(models.TextChoices):
        OUT_OF_RANGE = "out_of_range", "Fuera del radio del negocio"
        LOW_ACCURACY = "low_accuracy", "Precisión GPS insuficiente"
        MOCKED_LOCATION = "mocked_location", "Ubicación simulada"
        COOLDOWN = "cooldown", "Visita reciente en este negocio"
        DAILY_LIMIT = "daily_limit", "Límite diario de check-ins"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checkins", verbose_name="cliente"
    )
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="checkins", verbose_name="negocio"
    )
    status = models.CharField("estado", max_length=10, choices=Status.choices, db_index=True)
    reject_reason = models.CharField("motivo de rechazo", max_length=20, choices=RejectReason.choices, blank=True)
    latitude = models.DecimalField("latitud", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("longitud", max_digits=9, decimal_places=6)
    accuracy_m = models.PositiveIntegerField("precisión GPS (m)", null=True, blank=True)
    distance_m = models.PositiveIntegerField("distancia al negocio (m)")
    is_mocked = models.BooleanField("ubicación simulada", default=False)
    points_awarded = models.PositiveIntegerField("puntos otorgados", default=0)
    review_deadline = models.DateTimeField("reseñar hasta", null=True, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "check-in"
        verbose_name_plural = "check-ins"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "business", "status", "created_at"]),
            models.Index(fields=["business", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.client} → {self.business.name} ({self.get_status_display()})"

    def review_window_open(self, now) -> bool:
        return self.status == self.Status.AWARDED and self.review_deadline is not None and now <= self.review_deadline

    @staticmethod
    def deadline_from(created_at, hours: int):
        return created_at + timedelta(hours=hours)
