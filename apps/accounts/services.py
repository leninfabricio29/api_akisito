import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.emails import send_template_email, send_template_email_on_commit
from apps.core.exceptions import DomainError

from .models import PasswordResetCode, SignupCode, User


INVALID_SIGNUP_CODE = "Código inválido o expirado. Solicita uno nuevo."


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def request_signup_code(email: str, is_business: bool = False) -> None:
    """Paso 1 del registro: envía un código al correo. La cuenta aún no se crea."""
    email = email.lower().strip()
    if User.objects.filter(email=email).exists():
        raise DomainError(
            "Este correo ya tiene una cuenta. Inicia sesión o recupera tu contraseña.", code="email_taken"
        )

    SignupCode.objects.filter(email=email, used_at__isnull=True).update(used_at=timezone.now())
    raw_code = _new_code()
    signup = SignupCode(email=email, is_business=is_business, expires_at=timezone.now() + settings.SIGNUP_CODE_TTL)
    signup.set_code(raw_code)
    signup.save()

    send_template_email(
        email,
        "signup_code",
        {
            "code": raw_code,
            "is_business": is_business,
            "expires_minutes": int(settings.SIGNUP_CODE_TTL.total_seconds() // 60),
        },
    )


def _consume_signup_attempt(email: str, code: str) -> SignupCode | None:
    """Igual que con la recuperación: el intento fallido se guarda y no se lanza excepción aquí."""
    signup = (
        SignupCode.objects.select_for_update()
        .filter(email=email.lower().strip(), used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not signup or not signup.is_usable:
        return None
    if not signup.check_code(code):
        signup.attempts += 1
        signup.save(update_fields=["attempts"])
        return None
    return signup


def verify_signup_code(email: str, code: str) -> None:
    """Paso 2: confirma el código sin consumirlo (se consume al crear la contraseña)."""
    with transaction.atomic():
        signup = _consume_signup_attempt(email, code)
    if signup is None:
        raise DomainError(INVALID_SIGNUP_CODE, code="invalid_signup_code")


def complete_signup(email: str, code: str, password: str) -> User:
    """Paso 3: con el código válido crea la cuenta (cliente o negocio) con la contraseña elegida."""
    with transaction.atomic():
        signup = _consume_signup_attempt(email, code)
        user = None
        if signup is not None:
            if User.objects.filter(email=signup.email).exists():
                raise DomainError("Este correo ya tiene una cuenta. Inicia sesión.", code="email_taken")
            role = User.Role.BUSINESS if signup.is_business else User.Role.CLIENT
            user = User.objects.create_user(email=signup.email, password=password, role=role)
            signup.used_at = timezone.now()
            signup.save(update_fields=["used_at"])
            send_template_email_on_commit(
                user.email, "account_created", {"name": "", "email": user.email, "is_business": signup.is_business}
            )
    if user is None:
        raise DomainError(INVALID_SIGNUP_CODE, code="invalid_signup_code")
    return user


def request_password_reset(email: str) -> None:
    """Siempre responde igual exista o no la cuenta (evita enumerar usuarios)."""
    user = User.objects.filter(email=email.lower().strip(), is_active=True).first()
    if not user:
        return

    PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
    raw_code = _new_code()
    reset = PasswordResetCode(user=user, expires_at=timezone.now() + settings.PASSWORD_RESET_CODE_TTL)
    reset.set_code(raw_code)
    reset.save()

    send_template_email(
        user.email,
        "password_reset_code",
        {
            "name": user.get_full_name(),
            "code": raw_code,
            "expires_minutes": int(settings.PASSWORD_RESET_CODE_TTL.total_seconds() // 60),
        },
    )


INVALID_CODE = "Código inválido o expirado."


def _consume_attempt(email: str, code: str) -> PasswordResetCode | None:
    """
    Valida el código registrando el intento. Devuelve el registro si es correcto o None.
    No lanza excepciones para que el intento fallido quede guardado al confirmar la transacción.
    """
    reset = (
        PasswordResetCode.objects.select_for_update()
        .select_related("user")
        .filter(user__email=email.lower().strip(), user__is_active=True, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not reset or not reset.is_usable:
        return None
    if not reset.check_code(code):
        reset.attempts += 1
        reset.save(update_fields=["attempts"])
        return None
    return reset


def verify_reset_code(email: str, code: str) -> None:
    with transaction.atomic():
        reset = _consume_attempt(email, code)
    if reset is None:
        raise DomainError(INVALID_CODE, code="invalid_reset_code")


def reset_password(email: str, code: str, new_password: str, *, ip=None, device=None) -> None:
    with transaction.atomic():
        reset = _consume_attempt(email, code)
        if reset is not None:
            user = reset.user
            user.set_password(new_password)
            user.save(update_fields=["password", "updated_at"])
            reset.used_at = timezone.now()
            reset.save(update_fields=["used_at"])
    if reset is None:
        raise DomainError(INVALID_CODE, code="invalid_reset_code")
    notify_password_changed(user, ip=ip, device=device)


def change_password(user: User, new_password: str, *, ip=None, device=None) -> None:
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    notify_password_changed(user, ip=ip, device=device)


def notify_password_changed(user: User, *, ip=None, device=None) -> None:
    send_template_email(
        user.email, "password_changed", {"name": user.get_full_name(), "ip": ip, "device": (device or "")[:120]}
    )


@transaction.atomic
def delete_account(user: User) -> None:
    if user.is_business and hasattr(user, "business"):
        from apps.businesses.models import Business

        Business.objects.filter(pk=user.business.pk).update(
            status=Business.Status.SUSPENDED, status_reason="Cuenta del propietario eliminada"
        )
    user.devices.update(is_active=False)
    user.soft_delete()
