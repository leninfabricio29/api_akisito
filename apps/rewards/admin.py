from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import Redemption, Reward


@admin.register(Reward)
class RewardAdmin(ModelAdmin):
    list_display = ["title", "business", "points_required", "redeemed_count", "stock", "starts_at", "ends_at", "is_active"]
    list_filter = ["is_active", "starts_at"]
    search_fields = ["title", "business__name"]
    list_select_related = ["business"]
    autocomplete_fields = ["business"]
    readonly_fields = ["redeemed_count", "created_at", "updated_at"]


@admin.register(Redemption)
class RedemptionAdmin(ModelAdmin):
    list_display = ["code", "reward", "client", "points_spent", "status_label", "expires_at", "validated_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["code", "client__email", "reward__title", "business__name"]
    list_select_related = ["reward__business", "client"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @display(
        description="Estado",
        ordering="status",
        label={
            Redemption.Status.PENDING: "warning",
            Redemption.Status.VALIDATED: "success",
            Redemption.Status.EXPIRED: "danger",
            Redemption.Status.CANCELLED: "info",
        },
    )
    def status_label(self, obj):
        return obj.status, obj.get_status_display()
