from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import SingletonModel, TimeStampedModel
from apps.core.validators import validate_image_file


class BannerQuerySet(models.QuerySet):
    def visible(self, now=None):
        now = now or timezone.now()
        return self.filter(is_active=True).filter(
            models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now),
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now),
        )


class Banner(TimeStampedModel):
    """Publicidad de la plataforma que se muestra en el inicio de la app."""

    title = models.CharField("título", max_length=120, blank=True)
    image = models.ImageField("imagen", upload_to="banners/", validators=[validate_image_file])
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.SET_NULL, null=True, blank=True, related_name="banners",
        verbose_name="negocio enlazado", help_text="Opcional: al tocar el banner se abre este negocio.",
    )
    link_url = models.URLField("enlace externo", blank=True)
    order = models.PositiveSmallIntegerField("orden", default=0)
    is_active = models.BooleanField("activo", default=True)
    starts_at = models.DateTimeField("desde", null=True, blank=True)
    ends_at = models.DateTimeField("hasta", null=True, blank=True)

    objects = BannerQuerySet.as_manager()

    class Meta:
        verbose_name = "banner"
        verbose_name_plural = "banners"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title or f"Banner #{self.pk}"


version_format = RegexValidator(r"^\d+(\.\d+){0,2}$", "Usa el formato 1.2.3")


class AppVersion(SingletonModel):
    """
    Versión publicada en cada tienda. La app compara su versión instalada al abrirse:
    menor que «última versión» → sugiere actualizar; menor que «versión mínima» → obliga a actualizar.
    """

    android_latest_version = models.CharField(
        "Android · última versión", max_length=20, default="1.0.0", validators=[version_format],
        help_text="Actualízala cuando la nueva versión ya esté disponible en Google Play.",
    )
    android_min_version = models.CharField(
        "Android · versión mínima", max_length=20, blank=True, validators=[version_format],
        help_text="Opcional. Las versiones menores quedan bloqueadas hasta actualizar.",
    )
    android_store_url = models.URLField(
        "Android · enlace a Google Play",
        default="https://play.google.com/store/apps/details?id=com.anonymous.winner_app",
    )
    ios_latest_version = models.CharField(
        "iOS · última versión", max_length=20, default="1.0.0", validators=[version_format],
        help_text="Actualízala cuando la nueva versión ya esté disponible en el App Store.",
    )
    ios_min_version = models.CharField(
        "iOS · versión mínima", max_length=20, blank=True, validators=[version_format],
        help_text="Opcional. Las versiones menores quedan bloqueadas hasta actualizar.",
    )
    ios_store_url = models.URLField("iOS · enlace al App Store", blank=True)
    message = models.CharField(
        "mensaje", max_length=255,
        default="Hay una nueva versión de Akisito con mejoras y correcciones. Actualiza para seguir sumando puntos.",
    )

    class Meta:
        verbose_name = "versión de la app"
        verbose_name_plural = "versión de la app"

    def __str__(self):
        return "Versión de la app"

    def for_platform(self, platform: str) -> dict:
        prefix = "ios" if platform == "ios" else "android"
        return {
            "latest_version": getattr(self, f"{prefix}_latest_version"),
            "min_version": getattr(self, f"{prefix}_min_version") or None,
            "store_url": getattr(self, f"{prefix}_store_url") or None,
        }
