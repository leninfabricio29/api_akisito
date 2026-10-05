import base64

from django.core import signing
from django.db.models import Exists, OuterRef, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ConflictError
from apps.core.geo import bounding_box, haversine_m
from apps.core.permissions import IsApprovedBusiness, IsBusinessAccount, IsBusinessOwner, IsClient
from apps.loyalty.models import Membership
from apps.loyalty.services import get_settings

from . import services
from .models import Business, Category, Favorite
from .serializers import (
    BusinessDetailSerializer,
    BusinessListSerializer,
    BusinessCreateSerializer,
    CategorySerializer,
    FavoriteSerializer,
    OwnBusinessSerializer,
)

NEARBY_DEFAULT_RADIUS_M = 5_000
NEARBY_MAX_RADIUS_M = 50_000
NEARBY_MAX_RESULTS = 200


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True)
    pagination_class = None


def annotate_for_client(queryset, user):
    """Agrega is_favorite y my_points si quien consulta es un cliente autenticado."""
    if not (user and user.is_authenticated and user.is_client):
        return queryset
    return queryset.annotate(
        is_favorite=Exists(Favorite.objects.filter(client=user, business=OuterRef("pk"))),
        my_points=Subquery(
            Membership.objects.filter(client=user, business=OuterRef("pk")).values("points_balance")[:1]
        ),
    )


class NearbyQuerySerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    radius = serializers.IntegerField(
        min_value=100, max_value=NEARBY_MAX_RADIUS_M, default=NEARBY_DEFAULT_RADIUS_M
    )


class BusinessViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Directorio público de negocios aprobados.

    GET /businesses/?category=&search=         listado
    GET /businesses/?lat=&lng=&radius=         cercanos, ordenados por distancia
    GET /businesses/{id}/                      detalle
    """

    permission_classes = [AllowAny]
    filterset_fields = ["category"]
    search_fields = ["name", "description", "address", "category__name"]
    ordering_fields = ["name", "rating_avg", "created_at"]

    def get_queryset(self):
        queryset = (
            Business.objects.approved()
            .select_related("category")
            .order_by("-rating_avg", "name")
        )
        return annotate_for_client(queryset, self.request.user)

    def get_serializer_class(self):
        return BusinessDetailSerializer if self.action == "retrieve" else BusinessListSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "loyalty_settings": get_settings()}

    def list(self, request, *args, **kwargs):
        if "lat" not in request.query_params and "lng" not in request.query_params:
            return super().list(request, *args, **kwargs)

        params = NearbyQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        lat, lng, radius = params.validated_data["lat"], params.validated_data["lng"], params.validated_data["radius"]

        min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius)
        candidates = self.filter_queryset(self.get_queryset()).filter(
            latitude__range=(min_lat, max_lat), longitude__range=(min_lng, max_lng)
        )
        nearby = []
        for business in candidates[: NEARBY_MAX_RESULTS * 2]:
            business.distance_m = haversine_m(lat, lng, business.latitude, business.longitude)
            if business.distance_m <= radius:
                nearby.append(business)
        nearby.sort(key=lambda b: b.distance_m)

        page = self.paginate_queryset(nearby[:NEARBY_MAX_RESULTS])
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class FavoriteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """GET/POST /favorites/ · DELETE /favorites/{business_id}/"""

    permission_classes = [IsClient]
    serializer_class = FavoriteSerializer

    def get_queryset(self):
        return (
            Favorite.objects.filter(client=self.request.user, business__status=Business.Status.APPROVED)
            .select_related("business__category")
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "loyalty_settings": get_settings()}

    def perform_create(self, serializer):
        if Favorite.objects.filter(client=self.request.user, business=serializer.validated_data["business"]).exists():
            raise ConflictError("Este negocio ya está en tus favoritos.")
        serializer.save(client=self.request.user)

    def destroy(self, request, pk=None):
        deleted, _ = Favorite.objects.filter(client=request.user, business_id=pk).delete()
        if not deleted:
            return Response({"detail": "No está en tus favoritos.", "code": "not_found"}, status=404)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Portal del negocio ────────────────────────────────────────────────────────


class OwnBusinessView(APIView):
    """
    POST /business/        alta del negocio (una vez, tras registrarse); queda pendiente de aprobación
    GET/PATCH /business/   perfil del negocio del usuario autenticado
    """

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        return [IsBusinessAccount() if self.request.method == "POST" else IsBusinessOwner()]

    def post(self, request):
        serializer = BusinessCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        business = services.create_business(request.user, serializer.validated_data)
        return Response(OwnBusinessSerializer(business, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def get(self, request):
        return Response(OwnBusinessSerializer(request.user.business, context={"request": request}).data)

    def patch(self, request):
        serializer = OwnBusinessSerializer(
            request.user.business, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ResubmitBusinessView(APIView):
    permission_classes = [IsBusinessOwner]

    def post(self, request):
        business = services.resubmit(request.user.business)
        return Response(OwnBusinessSerializer(business, context={"request": request}).data)


class OwnBusinessQRViewSet(viewsets.ViewSet):
    """
    GET  /business/qr/          contenido del QR (la app del negocio puede dibujarlo)
    GET  /business/qr/image/    PNG listo para imprimir
    POST /business/qr/rotate/   invalida el QR anterior y genera uno nuevo
    """

    permission_classes = [IsApprovedBusiness]

    def list(self, request):
        business = request.user.business
        return Response({"payload": business.qr_payload, "rotated_at": business.qr_rotated_at})

    @action(detail=False, methods=["get"])
    def image(self, request):
        business = request.user.business
        response = HttpResponse(services.qr_png(business), content_type="image/png")
        response["Content-Disposition"] = f'inline; filename="qr-{business.ruc}.png"'
        return response

    @action(detail=False, methods=["post"])
    def rotate(self, request):
        business = request.user.business
        business.rotate_qr()
        return Response({"payload": business.qr_payload, "rotated_at": business.qr_rotated_at})

    @action(detail=False, methods=["post"])
    def poster(self, request):
        """Enlace temporal (10 min) a un afiche imprimible; la app lo abre en el navegador."""
        token = signing.dumps({"b": request.user.business.pk}, salt=POSTER_SALT)
        return Response({"url": request.build_absolute_uri(reverse("qr-poster", args=[token]))})


POSTER_SALT = "akisito.qr-poster"
POSTER_MAX_AGE_S = 10 * 60


def qr_poster(request, token):
    """Afiche HTML con el QR para imprimir o guardar como PDF desde el navegador."""
    try:
        data = signing.loads(token, salt=POSTER_SALT, max_age=POSTER_MAX_AGE_S)
    except signing.BadSignature:
        return HttpResponse("El enlace expiró. Vuelve a generarlo desde la app.", status=410, content_type="text/plain; charset=utf-8")
    business = get_object_or_404(Business.objects.approved(), pk=data["b"])
    qr = base64.b64encode(services.qr_png(business, box_size=14)).decode()
    return render(request, "businesses/qr_poster.html", {"business": business, "qr": qr})


def get_approved_business_or_404(pk):
    return get_object_or_404(Business.objects.approved(), pk=pk)
