from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import CheckIn


@admin.register(CheckIn)
class CheckInAdmin(ModelAdmin):
    list_display = [
        "created_at", "client", "business", "status_label", "reject_reason", "points_awarded",
        "distance_m", "accuracy_m", "is_mocked",
    ]
    list_filter = ["status", "reject_reason", "is_mocked", "created_at"]
    search_fields = ["client__email", "client__first_name", "client__last_name", "business__name"]
    list_select_related = ["client", "business"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(
        description="Estado",
        ordering="status",
        label={CheckIn.Status.AWARDED: "success", CheckIn.Status.REJECTED: "danger"},
    )
    def status_label(self, obj):
        return obj.status, obj.get_status_display()
