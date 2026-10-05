from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Device, Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ["created_at", "user", "kind", "title", "push_status", "read_at"]
    list_filter = ["kind", "push_status", "created_at"]
    search_fields = ["user__email", "title", "body"]
    list_select_related = ["user"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Device)
class DeviceAdmin(ModelAdmin):
    list_display = ["user", "platform", "name", "is_active", "last_seen_at"]
    list_filter = ["platform", "is_active"]
    search_fields = ["user__email", "token", "name"]
    list_select_related = ["user"]
    readonly_fields = ["token", "last_seen_at", "created_at"]
