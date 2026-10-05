from rest_framework.permissions import BasePermission


class IsClient(BasePermission):
    message = "Esta acción es solo para clientes."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_client)


class IsBusinessAccount(BasePermission):
    """Cuenta de tipo negocio, tenga o no su negocio creado todavía."""

    message = "Esta acción es solo para negocios."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_business)


class IsBusinessOwner(BasePermission):
    """Usuario de tipo negocio con su perfil de negocio creado (cualquier estado)."""

    message = "Esta acción es solo para negocios."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_business and hasattr(user, "business"))


class IsApprovedBusiness(IsBusinessOwner):
    """Negocio aprobado por el administrador: puede operar (recompensas, canjes, QR)."""

    message = "Tu negocio aún no ha sido aprobado."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.business.is_approved
