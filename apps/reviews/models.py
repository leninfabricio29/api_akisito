from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Review(TimeStampedModel):
    """Reseña ligada a una visita verificada. Los puntos no dependen de la calificación."""

    class Status(models.TextChoices):
        PUBLISHED = "published", "Publicada"
        HIDDEN = "hidden", "Oculta por moderación"

    checkin = models.OneToOneField(
        "checkins.CheckIn", on_delete=models.CASCADE, related_name="review", verbose_name="visita"
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews", verbose_name="cliente"
    )
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="reviews", verbose_name="negocio"
    )
    rating = models.PositiveSmallIntegerField(
        "calificación", validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField("comentario", blank=True, max_length=1000)
    points_awarded = models.PositiveIntegerField("puntos otorgados", default=0)
    status = models.CharField(
        "estado", max_length=10, choices=Status.choices, default=Status.PUBLISHED, db_index=True
    )
    moderation_note = models.CharField("nota de moderación", max_length=255, blank=True)
    reply = models.TextField("respuesta del negocio", blank=True, max_length=1000)
    replied_at = models.DateTimeField("respondida", null=True, blank=True)

    class Meta:
        verbose_name = "reseña"
        verbose_name_plural = "reseñas"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_5"),
        ]
        indexes = [models.Index(fields=["business", "status", "created_at"])]

    def __str__(self):
        return f"{self.rating}★ {self.client} → {self.business.name}"
