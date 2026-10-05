import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_file, validate_ruc_field

QR_SCHEME = "akisito://checkin/"


def generate_qr_token() -> str:
    return secrets.token_urlsafe(24)


class Category(TimeStampedModel):
    name = models.CharField("nombre", max_length=60, unique=True)
    icon = models.CharField("ícono", max_length=60, blank=True, help_text="Nombre del ícono usado por la app.")
    is_active = models.BooleanField("activa", default=True)
    order = models.PositiveSmallIntegerField("orden", default=0)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class BusinessQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(status=Business.Status.APPROVED, owner__is_active=True)


class Business(TimeStampedModel):
    """Negocio = un RUC = un local físico con su QR, ubicación y programa de puntos."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de aprobación"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        SUSPENDED = "suspended", "Suspendido"

    class TaxpayerType(models.TextChoices):
        NATURAL = "natural", "Persona natural"
        PRIVATE = "private", "Sociedad privada"
        PUBLIC = "public", "Entidad pública"

    # Borrar al propietario (solo lo hace un superusuario desde el admin) borra su negocio y todo su historial.
    # La app no borra: la eliminación de cuenta es lógica (User.soft_delete) y suspende el negocio.
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="business", verbose_name="propietario"
    )
    name = models.CharField("nombre comercial", max_length=120)
    ruc = models.CharField("RUC", max_length=13, unique=True, validators=[validate_ruc_field])
    taxpayer_type = models.CharField("tipo de contribuyente", max_length=10, choices=TaxpayerType.choices)
    ruc_checksum_ok = models.BooleanField(
        "verificador RUC correcto", default=True,
        help_text="Si es falso, el dígito verificador no cuadra: verifica el RUC en el SRI antes de aprobar.",
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="businesses", verbose_name="categoría")
    description = models.TextField("descripción", blank=True)
    logo = models.ImageField("logo", upload_to="businesses/logos/", blank=True, validators=[validate_image_file])
    cover = models.ImageField(
        "portada", upload_to="businesses/covers/", blank=True, validators=[validate_image_file],
        help_text="Imagen horizontal de cabecera en la página del negocio.",
    )

    address = models.CharField("dirección", max_length=255)
    latitude = models.DecimalField(
        "latitud", max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.DecimalField(
        "longitud", max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )

    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    status_reason = models.CharField("motivo del estado", max_length=255, blank=True)
    reviewed_at = models.DateTimeField("revisado", null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="revisado por",
    )
    announced_at = models.DateTimeField(
        "anunciado a los clientes", null=True, blank=True,
        help_text="Push de «nuevo negocio» enviado en la primera aprobación; no se repite al reaprobar.",
    )

    qr_token = models.CharField("token QR", max_length=64, unique=True, default=generate_qr_token, editable=False)
    qr_rotated_at = models.DateTimeField("QR regenerado", null=True, blank=True)

    # Reglas propias del negocio (vacío = usar la configuración global).
    checkin_points = models.PositiveSmallIntegerField(
        "puntos por visita", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(500)]
    )
    review_points = models.PositiveSmallIntegerField(
        "puntos por reseña", null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(500)]
    )
    checkin_radius_m = models.PositiveSmallIntegerField(
        "radio de check-in (m)", null=True, blank=True, validators=[MinValueValidator(30), MaxValueValidator(1000)]
    )

    # Denormalizado; lo mantiene el servicio de reseñas.
    rating_avg = models.DecimalField("calificación promedio", max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField("número de reseñas", default=0)

    objects = BusinessQuerySet.as_manager()

    class Meta:
        verbose_name = "negocio"
        verbose_name_plural = "negocios"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["latitude", "longitude"])]

    def __str__(self):
        return f"{self.name} ({self.ruc})"

    @property
    def is_approved(self) -> bool:
        return self.status == self.Status.APPROVED

    @property
    def location_locked(self) -> bool:
        """La ubicación solo se elige antes de la aprobación; después la cambia el administrador."""
        return self.status not in (self.Status.PENDING, self.Status.REJECTED)

    @property
    def qr_payload(self) -> str:
        return f"{QR_SCHEME}{self.qr_token}"

    def rotate_qr(self):
        from django.utils import timezone

        self.qr_token = generate_qr_token()
        self.qr_rotated_at = timezone.now()
        self.save(update_fields=["qr_token", "qr_rotated_at", "updated_at"])


class Favorite(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites", verbose_name="cliente"
    )
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="favorited_by", verbose_name="negocio")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "favorito"
        verbose_name_plural = "favoritos"
        constraints = [models.UniqueConstraint(fields=["client", "business"], name="unique_favorite")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.client} ♥ {self.business}"
