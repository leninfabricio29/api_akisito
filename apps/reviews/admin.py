from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from . import services
from .models import Review


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ["created_at", "business", "client", "stars", "short_comment", "points_awarded", "status_label"]
    list_filter = ["status", "rating", "created_at"]
    search_fields = ["comment", "business__name", "client__email"]
    list_select_related = ["business", "client"]
    readonly_fields = ["checkin", "client", "business", "rating", "comment", "points_awarded", "reply", "replied_at",
                       "created_at"]
    fields = ["business", "client", "checkin", "rating", "comment", "points_awarded", "reply", "replied_at",
              "status", "moderation_note", "created_at"]
    actions = ["hide_selected", "publish_selected"]

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.refresh_business_rating(obj.business_id)

    @display(description="Calificación", ordering="rating")
    def stars(self, obj):
        return "★" * obj.rating + "☆" * (5 - obj.rating)

    @display(description="Comentario")
    def short_comment(self, obj):
        return (obj.comment[:60] + "…") if len(obj.comment) > 60 else obj.comment

    @display(description="Estado", label={Review.Status.PUBLISHED: "success", Review.Status.HIDDEN: "danger"})
    def status_label(self, obj):
        return obj.status, obj.get_status_display()

    @action(description="Ocultar reseñas seleccionadas", icon="visibility_off")
    def hide_selected(self, request, queryset):
        for review in queryset:
            services.set_visibility(review, hidden=True, note=f"Moderada por {request.user.email}")
        messages.success(request, f"{queryset.count()} reseña(s) ocultas.")

    @action(description="Publicar reseñas seleccionadas", icon="visibility")
    def publish_selected(self, request, queryset):
        for review in queryset:
            services.set_visibility(review, hidden=False)
        messages.success(request, f"{queryset.count()} reseña(s) publicadas.")
