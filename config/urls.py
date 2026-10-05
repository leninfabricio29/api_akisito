from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.businesses.views import qr_poster


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("qr-poster/<str:token>/", qr_poster, name="qr-poster"),
    path("api/v1/", include("config.api_urls")),
]
