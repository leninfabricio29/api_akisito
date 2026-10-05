from rest_framework_simplejwt.tokens import RefreshToken


def tokens_for(user) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
