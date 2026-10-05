from django import forms
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminIntegerFieldWidget, UnfoldAdminTextInputWidget

from apps.core.exceptions import DomainError

from .models import LoyaltySettings, Membership, PointTransaction
from .services import adjust_points


@admin.register(LoyaltySettings)
class LoyaltySettingsAdmin(ModelAdmin):
    fieldsets = (
        ("Puntos", {"fields": ("checkin_points", "review_points")}),
        ("Check-in", {"fields": ("checkin_cooldown_hours", "max_checkins_per_day", "checkin_radius_m", "max_gps_accuracy_m")}),
        ("Reseñas", {"fields": ("review_window_hours", "review_points_cooldown_days")}),
        ("Retención", {"fields": ("winback_enabled", "winback_days", "points_expiration_enabled", "points_expire_after_days")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = LoyaltySettings.load()
        return redirect(reverse("admin:loyalty_loyaltysettings_change", args=[obj.pk]))


class PointTransactionInline(TabularInline):
    model = PointTransaction
    extra = 0
    fields = ["created_at", "kind", "points", "balance_after", "description", "created_by"]
    readonly_fields = fields
    can_delete = False
    ordering = ["-created_at"]
    max_num = 0
    per_page = 20

    def has_add_permission(self, request, obj=None):
        return False


class AdjustPointsForm(forms.Form):
    points = forms.IntegerField(
        label="Puntos", help_text="Positivo para sumar, negativo para restar.", widget=UnfoldAdminIntegerFieldWidget
    )
    description = forms.CharField(label="Motivo", max_length=200, widget=UnfoldAdminTextInputWidget)

    def clean_points(self):
        value = self.cleaned_data["points"]
        if value == 0:
            raise forms.ValidationError("Debe ser distinto de 0.")
        return value


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = ["client", "business", "points_balance", "lifetime_points", "checkins_count", "last_checkin_at"]
    list_filter = ["business__category", "last_checkin_at"]
    search_fields = ["client__email", "client__first_name", "client__last_name", "business__name"]
    list_select_related = ["client", "business"]
    readonly_fields = [
        "client", "business", "points_balance", "lifetime_points", "checkins_count", "reviews_count",
        "redemptions_count", "first_checkin_at", "last_checkin_at", "last_activity_at", "winback_sent_at",
        "created_at",
    ]
    inlines = [PointTransactionInline]
    actions_detail = ["adjust"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Solo superusuarios: borra también sus movimientos y canjes.
        return request.user.is_superuser

    def get_urls(self):
        custom = [
            path(
                "<int:object_id>/adjust/",
                self.admin_site.admin_view(self.adjust_view),
                name="loyalty_membership_adjust",
            )
        ]
        return custom + super().get_urls()

    @action(description="Ajustar puntos", icon="exposure")
    def adjust(self, request, object_id):
        return redirect(reverse("admin:loyalty_membership_adjust", args=[object_id]))

    def adjust_view(self, request, object_id):
        membership = get_object_or_404(Membership.objects.select_related("client", "business"), pk=object_id)
        form = AdjustPointsForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                adjust_points(membership.pk, form.cleaned_data["points"], form.cleaned_data["description"], request.user)
            except DomainError as exc:
                form.add_error("points", str(exc.detail))
            else:
                messages.success(request, "Ajuste registrado.")
                return redirect(reverse("admin:loyalty_membership_change", args=[object_id]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Ajustar puntos · {membership.client.get_full_name()} en {membership.business.name}",
            "membership": membership,
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/loyalty/adjust_points.html", context)


@admin.register(PointTransaction)
class PointTransactionAdmin(ModelAdmin):
    list_display = ["created_at", "client", "business", "kind_label", "points", "balance_after", "description"]
    list_filter = ["kind", "created_at"]
    search_fields = ["membership__client__email", "membership__business__name", "description"]
    list_select_related = ["membership__client", "membership__business"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Necesario para que un superusuario pueda borrar usuarios, negocios o membresías (que arrastran
        # sus movimientos). Borrar movimientos sueltos descuadraría el saldo: se ocultan esas opciones.
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url, {**(extra_context or {}), "show_delete": False})

    def delete_view(self, request, object_id, extra_context=None):
        messages.error(request, "Los movimientos no se borran sueltos: usa «Ajustar puntos» en la membresía.")
        return redirect(reverse("admin:loyalty_pointtransaction_changelist"))

    @display(description="Cliente")
    def client(self, obj):
        return obj.membership.client

    @display(description="Negocio")
    def business(self, obj):
        return obj.membership.business.name

    @display(
        description="Tipo",
        label={
            PointTransaction.Kind.CHECKIN: "success",
            PointTransaction.Kind.REVIEW: "info",
            PointTransaction.Kind.REDEMPTION: "warning",
            PointTransaction.Kind.REFUND: "info",
            PointTransaction.Kind.ADJUSTMENT: "danger",
            PointTransaction.Kind.EXPIRATION: "danger",
        },
    )
    def kind_label(self, obj):
        return obj.kind, obj.get_kind_display()
