from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsClient
from apps.core.throttles import CheckInRateThrottle

from . import services
from .models import CheckIn
from .serializers import CheckInSerializer, ScanSerializer, scan_response


class ScanView(APIView):
    """
    POST /checkins/scan/

    El cliente escanea el QR; la app envía el contenido y su ubicación.
    Responde con los puntos ganados y la invitación a reseñar.
    """

    permission_classes = [IsClient]
    throttle_classes = [CheckInRateThrottle]

    def post(self, request):
        serializer = ScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.scan(
            request.user,
            qr=data["qr"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            accuracy_m=data.get("accuracy"),
            is_mocked=data["is_mocked"],
        )
        return Response(scan_response(result, request), status=status.HTTP_201_CREATED)


class MyCheckInsView(generics.ListAPIView):
    """GET /checkins/?business=<id> — historial de visitas del cliente."""

    permission_classes = [IsClient]
    serializer_class = CheckInSerializer
    filterset_fields = ["business"]
    search_fields = []

    def get_queryset(self):
        return (
            CheckIn.objects.filter(client=self.request.user, status=CheckIn.Status.AWARDED)
            .select_related("business", "review")
        )
