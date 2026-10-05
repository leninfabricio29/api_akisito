from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_file


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("El email es obligatorio.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", User.Role.CLIENT)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        extra.setdefault("first_name", "Admin")
        extra.setdefault("last_name", "Akisito")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        BUSINESS = "business", "Negocio"
        CLIENT = "client", "Cliente"

    email = models.EmailField("email", unique=True)
    # Vacíos al registrarse (solo se pide el correo); la app obliga a completarlos después.
    first_name = models.CharField("nombres", max_length=80, blank=True)
    last_name = models.CharField("apellidos", max_length=80, blank=True)
    phone = models.CharField("teléfono", max_length=20, blank=True)
    ci = models.CharField("cédula", max_length=10, unique=True, null=True, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    avatar = models.ImageField("avatar", upload_to="avatars/", blank=True, validators=[validate_image_file])
    role = models.CharField("rol", max_length=10, choices=Role.choices, default=Role.CLIENT, db_index=True)

    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField("acceso al admin", default=False)
    deleted_at = models.DateTimeField("eliminado", null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def is_client(self):
        return self.role == self.Role.CLIENT

    @property
    def is_business(self):
        return self.role == self.Role.BUSINESS

    @property
    def pending_steps(self) -> list[str]:
        """Pasos que la app obliga a completar tras el registro: "profile" y, si es negocio, "business"."""
        steps = []
        if not (self.first_name and self.last_name and self.phone):
            steps.append("profile")
        if self.is_business and not hasattr(self, "business"):
            steps.append("business")
        return steps

    def soft_delete(self):
        """Elimina la cuenta conservando el historial (puntos, check-ins) de forma anónima."""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.email = f"deleted-{self.pk}@akisito.invalid"
        self.ci = None
        self.phone = ""
        self.first_name = "Usuario"
        self.last_name = "eliminado"
        self.set_unusable_password()
        self.save()


class PasswordResetCode(models.Model):
    """Código de 6 dígitos para recuperar contraseña. Se guarda hasheado y con intentos limitados."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reset_codes")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "código de recuperación"
        verbose_name_plural = "códigos de recuperación"
        ordering = ["-created_at"]

    def set_code(self, raw_code: str):
        self.code_hash = make_password(raw_code)

    def check_code(self, raw_code: str) -> bool:
        return check_password(raw_code, self.code_hash)

    @property
    def is_usable(self) -> bool:
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.attempts < settings.PASSWORD_RESET_MAX_ATTEMPTS
        )


class SignupCode(models.Model):
    """
    Código de 6 dígitos que verifica el correo antes de crear la cuenta.
    El usuario no existe hasta que el código se valida y elige su contraseña.
    """

    email = models.EmailField("email", db_index=True)
    is_business = models.BooleanField("quiere registrar un negocio", default=False)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "código de registro"
        verbose_name_plural = "códigos de registro"
        ordering = ["-created_at"]

    def set_code(self, raw_code: str):
        self.code_hash = make_password(raw_code)

    def check_code(self, raw_code: str) -> bool:
        return check_password(raw_code, self.code_hash)

    @property
    def is_usable(self) -> bool:
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.attempts < settings.PASSWORD_RESET_MAX_ATTEMPTS
        )
