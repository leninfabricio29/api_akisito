from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from unfold.admin import ModelAdmin

from .models import AppVersion, Banner


@admin.register(Banner)
class BannerAdmin(ModelAdmin):
    list_display = ["__str__", "business", "order", "is_active", "starts_at", "ends_at"]
    list_editable = ["order", "is_active"]
    list_filter = ["is_active"]
    autocomplete_fields = ["business"]


@admin.register(AppVersion)
class AppVersionAdmin(ModelAdmin):
    fieldsets = (
        ("Android", {"fields": ("android_latest_version", "android_min_version", "android_store_url")}),
        ("iOS", {"fields": ("ios_latest_version", "ios_min_version", "ios_store_url")}),
        ("Aviso", {"fields": ("message",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = AppVersion.load()
        return redirect(reverse("admin:content_appversion_change", args=[obj.pk]))
