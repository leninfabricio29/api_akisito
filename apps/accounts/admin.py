from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(ModelAdmin):
    search_fields = ["name"]
    filter_horizontal = ["permissions"]


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["email", "full_name", "role_label", "phone", "is_active", "created_at"]
    list_filter = ["role", "is_active", "is_staff", "created_at"]
    search_fields = ["email", "first_name", "last_name", "ci", "phone"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "last_login", "deleted_at"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "ci", "phone", "birth_date", "avatar")}),
        ("Rol y acceso", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Fechas", {"fields": ("last_login", "created_at", "updated_at", "deleted_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),
    )

    @display(description="Nombre", ordering="first_name")
    def full_name(self, obj):
        return obj.get_full_name()

    @display(
        description="Rol",
        ordering="role",
        label={User.Role.ADMIN: "danger", User.Role.BUSINESS: "warning", User.Role.CLIENT: "info"},
    )
    def role_label(self, obj):
        return obj.role, obj.get_role_display()
