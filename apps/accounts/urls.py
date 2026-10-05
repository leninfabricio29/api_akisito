from django.urls import path

from . import views

urlpatterns = [
    path("auth/register/start/", views.SignupStartView.as_view(), name="signup-start"),
    path("auth/register/verify/", views.SignupVerifyView.as_view(), name="signup-verify"),
    path("auth/register/complete/", views.SignupCompleteView.as_view(), name="signup-complete"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("auth/password/change/", views.ChangePasswordView.as_view(), name="password-change"),
    path("auth/password/forgot/", views.ForgotPasswordView.as_view(), name="password-forgot"),
    path("auth/password/verify/", views.VerifyResetCodeView.as_view(), name="password-verify"),
    path("auth/password/reset/", views.ResetPasswordView.as_view(), name="password-reset"),
    path("me/", views.MeView.as_view(), name="me"),
]
