from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Notification
from .serializers import DeviceSerializer, DeviceTokenSerializer, NotificationSerializer


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET  /notifications/?kind=&unread=true
    GET  /notifications/unread-count/
    POST /notifications/{id}/read/
    POST /notifications/read-all/
    """

    serializer_class = NotificationSerializer
    filterset_fields = ["kind"]
    search_fields = []

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": Notification.objects.filter(user=request.user, read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        updated = Notification.objects.filter(user=request.user, pk=pk, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        if not updated and not Notification.objects.filter(user=request.user, pk=pk).exists():
            return Response({"detail": "Notificación no encontrada.", "code": "not_found"}, status=404)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        count = Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": count})


class DeviceView(APIView):
    """POST /devices/ registra el token FCM · DELETE /devices/ lo desactiva (al cerrar sesión)."""

    def post(self, request):
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.register_device(request.user, **serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.unregister_device(request.user, serializer.validated_data["token"])
        return Response(status=status.HTTP_204_NO_CONTENT)
