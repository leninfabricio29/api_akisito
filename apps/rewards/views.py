from django.db import transaction
from django.db.models import OuterRef, Subquery
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.businesses.views import get_approved_business_or_404
from apps.core.permissions import IsApprovedBusiness, IsBusinessOwner, IsClient
from apps.loyalty.models import Membership

from . import services
from .models import Redemption, Reward
from .serializers import (
    BusinessRedemptionSerializer,
    OwnRewardSerializer,
    RedemptionSerializer,
    RewardSerializer,
    ValidateCodeSerializer,
)


def _with_my_points(queryset, user):
    if not (user and user.is_authenticated and user.is_client):
        return queryset
    return queryset.annotate(
        my_points=Subquery(
            Membership.objects.filter(client=user, business=OuterRef("business")).values("points_balance")[:1]
        )
    )


class RewardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /rewards/?business=&search=     recompensas disponibles (con mis puntos en cada negocio)
    GET  /rewards/{id}/
    POST /rewards/{id}/redeem/           genera el código de canje
    """

    serializer_class = RewardSerializer
    filterset_fields = ["business"]
    search_fields = ["title", "description", "business__name"]
    ordering_fields = ["points_required", "created_at"]

    def get_permissions(self):
        return [IsClient()] if self.action == "redeem" else [AllowAny()]

    def get_queryset(self):
        return _with_my_points(Reward.objects.available().select_related("business"), self.request.user)

    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        redemption = services.redeem(request.user, int(pk))
        redemption = Redemption.objects.select_related("reward", "business").get(pk=redemption.pk)
        return Response(RedemptionSerializer(redemption).data, status=status.HTTP_201_CREATED)


class BusinessRewardsView(generics.ListAPIView):
    """GET /businesses/{id}/rewards/"""

    permission_classes = [AllowAny]
    serializer_class = RewardSerializer
    search_fields = []

    def get_queryset(self):
        business = get_approved_business_or_404(self.kwargs["business_id"])
        return _with_my_points(
            Reward.objects.available().filter(business=business).select_related("business"), self.request.user
        )


class MyRedemptionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """GET /redemptions/?status= · POST /redemptions/{id}/cancel/"""

    permission_classes = [IsClient]
    serializer_class = RedemptionSerializer
    filterset_fields = ["status", "business"]
    search_fields = []

    def get_queryset(self):
        return Redemption.objects.filter(client=self.request.user).select_related("reward", "business")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        services.cancel(request.user, int(pk))
        return Response(self.get_serializer(self.get_queryset().get(pk=pk)).data)


class OwnRewardViewSet(viewsets.ModelViewSet):
    """CRUD de recompensas del negocio. DELETE desactiva si ya tiene canjes."""

    serializer_class = OwnRewardSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ["is_active"]
    search_fields = ["title"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsBusinessOwner()]
        return [IsApprovedBusiness()]

    def get_queryset(self):
        return Reward.objects.filter(business=self.request.user.business)

    def perform_create(self, serializer):
        with transaction.atomic():
            reward = serializer.save(business=self.request.user.business)
            if reward.is_active:
                transaction.on_commit(lambda: services.notify_new_reward(reward))

    def perform_destroy(self, instance):
        if instance.redemptions.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        else:
            instance.delete()


class OwnRedemptionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET  /business/redemptions/?status=
    GET  /business/redemptions/lookup/?code=   ver el canje antes de validarlo
    POST /business/redemptions/validate/
    """

    serializer_class = BusinessRedemptionSerializer
    filterset_fields = ["status", "reward"]
    search_fields = ["code", "client__first_name", "client__last_name"]

    def get_permissions(self):
        return [IsApprovedBusiness()] if self.action == "validate" else [IsBusinessOwner()]

    def get_queryset(self):
        return Redemption.objects.filter(business=self.request.user.business).select_related(
            "reward", "business", "client"
        )

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        code = (request.query_params.get("code") or "").strip().upper()
        redemption = self.get_queryset().filter(code=code).first() if code else None
        if redemption is None:
            return Response({"detail": "Código de canje no encontrado.", "code": "redemption_not_found"}, status=404)
        return Response(self.get_serializer(redemption).data)

    @action(detail=False, methods=["post"])
    def validate(self, request):
        serializer = ValidateCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        redemption = services.validate_code(request.user.business, serializer.validated_data["code"], request.user)
        return Response(self.get_serializer(self.get_queryset().get(pk=redemption.pk)).data)
