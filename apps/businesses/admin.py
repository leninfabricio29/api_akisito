import base64

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from apps.core.exceptions import DomainError

from . import services
from .models import Business, Category, Favorite


def pending_businesses_badge(request):
    count = Business.objects.filter(status=Business.Status.PENDING).count()
    return count or None


@admin.register(Business)
class BusinessAdmin(ModelAdmin):
    list_display = ["name", "ruc", "ruc_check", "category", "status_label", "rating_avg", "owner", "created_at"]
    list_filter = ["status", "category", "ruc_checksum_ok", "taxpayer_type", "created_at"]
    search_fields = ["name", "ruc", "owner__email", "address"]
    list_select_related = ["category", "owner"]
    autocomplete_fields = ["owner", "category"]
    actions = ["approve_selected"]
    actions_detail = ["download_qr", "rotate_qr"]
    readonly_fields = [
        "taxpayer_type", "ruc_checksum_ok", "reviewed_at", "reviewed_by", "announced_at", "rating_avg", "rating_count",
        "qr_preview", "qr_rotated_at", "created_at", "updated_at",
    ]
    fieldsets = (
        ("Negocio", {"fields": ("owner", "name", "category", "description", "logo", "cover")}),
        ("RUC", {"fields": ("ruc", "taxpayer_type", "ruc_checksum_ok")}),
        ("Aprobación", {
            "fields": ("status", "status_reason", "reviewed_at", "reviewed_by", "announced_at"),
            "description": "Para rechazar o suspender escribe el motivo: se envía al propietario por correo. La primera aprobación avisa por push a todos los clientes.",
        }),
        ("Ubicación", {
            "fields": ("address", "latitude", "longitude"),
            "description": "El negocio solo puede cambiar su ubicación antes de ser aprobado; después, solo desde aquí.",
        }),
        ("Programa de puntos", {
            "fields": ("checkin_points", "review_points", "checkin_radius_m"),
            "description": "Déjalo vacío para usar la configuración global.",
        }),
        ("QR", {"fields": ("qr_preview", "qr_rotated_at")}),
        ("Reputación", {"fields": ("rating_avg", "rating_count", "created_at", "updated_at")}),
    )

    @display(description="Verificador RUC", label={"ok": "success", "revisar": "warning"})
    def ruc_check(self, obj):
        return ("ok", "OK") if obj.ruc_checksum_ok else ("revisar", "Revisar en SRI")

    @display(
        description="Estado",
        ordering="status",
        label={
            Business.Status.PENDING: "warning",
            Business.Status.APPROVED: "success",
            Business.Status.REJECTED: "danger",
            Business.Status.SUSPENDED: "danger",
        },
    )
    def status_label(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Vista previa")
    def qr_preview(self, obj):
        if not obj.pk:
            return "-"
        png = base64.b64encode(services.qr_png(obj, box_size=6)).decode()
        return format_html('<img src="data:image/png;base64,{}" alt="QR" style="width:180px;height:180px">', png)

    def save_model(self, request, obj, form, change):
        """Los cambios de estado pasan por el servicio: valida el motivo y notifica al propietario."""
        new_status = obj.status
        status_changed = change and "status" in form.changed_data
        if status_changed:
            obj.status = form.initial["status"]
        super().save_model(request, obj, form, change)
        if status_changed:
            try:
                services.set_status(obj, new_status, reason=obj.status_reason, by=request.user)
            except DomainError as exc:
                messages.error(request, f"No se cambió el estado: {exc.detail}")

    @action(description="Aprobar negocios seleccionados", icon="check_circle")
    def approve_selected(self, request, queryset):
        approved = 0
        for business in queryset.exclude(status=Business.Status.APPROVED):
            try:
                services.set_status(business, Business.Status.APPROVED, by=request.user)
                approved += 1
            except (DomainError, ValidationError) as exc:
                messages.error(request, f"{business.name}: {exc}")
        messages.success(request, f"{approved} negocio(s) aprobado(s).")

    @action(description="Descargar QR", icon="qr_code_2")
    def download_qr(self, request, object_id):
        business = Business.objects.get(pk=object_id)
        response = HttpResponse(services.qr_png(business), content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="qr-{business.ruc}.png"'
        return response

    @action(description="Regenerar QR", icon="autorenew")
    def rotate_qr(self, request, object_id):
        business = Business.objects.get(pk=object_id)
        business.rotate_qr()
        messages.warning(request, "QR regenerado: el QR impreso anterior dejó de funcionar.")
        return redirect(reverse("admin:businesses_business_change", args=[object_id]))


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ["name", "icon", "order", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["name"]


@admin.register(Favorite)
class FavoriteAdmin(ModelAdmin):
    list_display = ["client", "business", "created_at"]
    search_fields = ["client__email", "business__name"]
    list_select_related = ["client", "business"]
    autocomplete_fields = ["client", "business"]
