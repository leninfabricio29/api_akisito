from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = "password_reset"


class SignupRateThrottle(AnonRateThrottle):
    scope = "signup"


class CheckInRateThrottle(UserRateThrottle):
    scope = "checkin"
