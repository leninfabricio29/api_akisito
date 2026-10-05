from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.validators import validate_cedula

from .models import User


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(read_only=True)
    business = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "phone", "ci", "birth_date",
            "avatar", "role", "business", "pending_steps", "created_at",
        ]
        read_only_fields = fields

    def get_business(self, user):
        business = getattr(user, "business", None) if user.is_business else None
        if not business:
            return None
        return {"id": business.pk, "name": business.name, "status": business.status}


class UpdateMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "ci", "birth_date", "avatar"]
        extra_kwargs = {
            "avatar": {"required": False},
            # Opcionales al registrarse, pero una vez ingresados no se pueden dejar vacíos.
            "first_name": {"allow_blank": False},
            "last_name": {"allow_blank": False},
            "phone": {"allow_blank": False},
        }

    def validate_ci(self, value):
        if not value:
            return None
        if self.instance.ci and self.instance.ci != value:
            raise serializers.ValidationError("La cédula no se puede cambiar; contacta a soporte.")
        try:
            value = validate_cedula(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.objects.filter(ci=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Esta cédula ya está registrada.")
        return value


class PasswordField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("write_only", True)
        kwargs.setdefault("trim_whitespace", False)
        kwargs.setdefault("style", {"input_type": "password"})
        super().__init__(**kwargs)


def _validate_new_password(password, user=None):
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc
    return password


class SignupStartSerializer(serializers.Serializer):
    email = serializers.EmailField()
    is_business = serializers.BooleanField(default=False)


class SignupVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "El código tiene 6 dígitos."})


class SignupCompleteSerializer(SignupVerifySerializer):
    password = PasswordField()

    def validate(self, attrs):
        try:
            _validate_new_password(attrs["password"], User(email=attrs["email"]))
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail}) from exc
        return attrs


class LoginSerializer(TokenObtainPairSerializer):
    default_error_messages = {"no_active_account": "Credenciales inválidas o cuenta inactiva."}

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].lower().strip()
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token


class ChangePasswordSerializer(serializers.Serializer):
    current_password = PasswordField()
    new_password = PasswordField()

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate(self, attrs):
        _validate_new_password(attrs["new_password"], self.context["request"].user)
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyResetCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "El código tiene 6 dígitos."})


class ResetPasswordSerializer(VerifyResetCodeSerializer):
    new_password = PasswordField()

    def validate(self, attrs):
        _validate_new_password(attrs["new_password"])
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    password = PasswordField()

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Contraseña incorrecta.")
        return value
