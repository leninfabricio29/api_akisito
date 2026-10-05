from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AppVersion, Banner
from .serializers import BannerSerializer


class BannerListView(generics.ListAPIView):
    """GET /banners/ — banners vigentes para el inicio de la app."""

    permission_classes = [AllowAny]
    serializer_class = BannerSerializer
    pagination_class = None
    filter_backends = []

    def get_queryset(self):
        return Banner.objects.visible()


class AppVersionView(APIView):
    """GET /app/version/ — versión vigente por plataforma (la app avisa si la instalada es anterior)."""

    permission_classes = [AllowAny]

    def get(self, request):
        config = AppVersion.load()
        return Response(
            {"android": config.for_platform("android"), "ios": config.for_platform("ios"), "message": config.message}
        )
