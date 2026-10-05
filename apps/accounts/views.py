from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.throttles import AuthRateThrottle, PasswordResetRateThrottle, SignupRateThrottle

from . import services
from .serializers import (
    ChangePasswordSerializer,
    DeleteAccountSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    ResetPasswordSerializer,
    SignupCompleteSerializer,
    SignupStartSerializer,
    SignupVerifySerializer,
    UpdateMeSerializer,
    UserSerializer,
    VerifyResetCodeSerializer,
)
from .tokens import tokens_for


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _device(request):
    return request.META.get("HTTP_USER_AGENT", "")


class SignupStartView(APIView):
    """Registro, paso 1: solo el correo (y si quiere registrar un negocio). Envía el código."""

    permission_classes = [AllowAny]
    throttle_classes = [SignupRateThrottle]

    def post(self, request):
        serializer = SignupStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_signup_code(**serializer.validated_data)
        return Response({"detail": "Te enviamos un código de verificación a tu correo."})


class SignupVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_signup_code(**serializer.validated_data)
        return Response({"valid": True})


class SignupCompleteView(APIView):
    """Registro, paso 3: crea la cuenta con la contraseña elegida e inicia sesión."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = SignupCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.complete_signup(**serializer.validated_data)
        return Response(
            {**tokens_for(user), "user": UserSerializer(user, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [AuthRateThrottle]


class RefreshView(TokenRefreshView):
    throttle_classes = [AuthRateThrottle]


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = UpdateMeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.delete_account(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.change_password(
            request.user, serializer.validated_data["new_password"], ip=_client_ip(request), device=_device(request)
        )
        return Response({"detail": "Contraseña actualizada."})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response({"detail": "Si el correo está registrado, te enviamos un código de recuperación."})


class VerifyResetCodeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = VerifyResetCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_reset_code(**serializer.validated_data)
        return Response({"valid": True})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_password(**serializer.validated_data, ip=_client_ip(request), device=_device(request))
        return Response({"detail": "Contraseña actualizada. Ya puedes iniciar sesión."})
