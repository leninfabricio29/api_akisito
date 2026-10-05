from datetime import timedelta

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import ValidationError

from apps.core.permissions import IsBusinessOwner, IsClient
from apps.rewards.models import Reward

from .models import Membership, PointTransaction
from .serializers import CustomerSerializer, PointTransactionSerializer, WalletSerializer


def _attach_next_reward(memberships):
    """Para cada monedero, la recompensa más barata que aún no alcanza (motiva a volver)."""
    memberships = list(memberships)
    business_ids = {m.business_id for m in memberships}
    rewards = list(Reward.objects.available().filter(business_id__in=business_ids).order_by("points_required"))
    for membership in memberships:
        membership.next_reward_obj = next(
            (r for r in rewards if r.business_id == membership.business_id and r.points_required > membership.points_balance),
            None,
        )
    return memberships


class WalletListView(generics.ListAPIView):
    """GET /wallets/ — puntos del cliente en cada negocio que ha visitado."""

    permission_classes = [IsClient]
    serializer_class = WalletSerializer
    search_fields = ["business__name"]
    ordering_fields = ["points_balance", "last_checkin_at"]

    def get_queryset(self):
        now = timezone.now()
        redeemable = (
            Reward.objects.available(now)
            .filter(business=OuterRef("business"), points_required__lte=OuterRef("points_balance"))
            .values("business")
            .annotate(c=Count("pk"))
            .values("c")[:1]
        )
        return (
            Membership.objects.filter(client=self.request.user, business__status="approved")
            .select_related("business__category")
            .annotate(redeemable_rewards=Subquery(redeemable))
            .order_by(F("last_checkin_at").desc(nulls_last=True))
        )

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        data = self.get_serializer(_attach_next_reward(page), many=True).data
        return self.get_paginated_response(data)


class WalletTransactionsView(generics.ListAPIView):
    """GET /wallets/{business_id}/transactions/ — movimientos de puntos en un negocio."""

    permission_classes = [IsClient]
    serializer_class = PointTransactionSerializer
    filterset_fields = ["kind"]
    search_fields = []

    def get_queryset(self):
        membership = get_object_or_404(Membership, client=self.request.user, business_id=self.kwargs["business_id"])
        return PointTransaction.objects.filter(membership=membership)


class CustomerListView(generics.ListAPIView):
    """
    GET /business/customers/?segment=&search=&ordering=

    Segmentos:
      new       primera visita en los últimos 30 días
      frequent  3+ visitas y activo en los últimos 30 días
      at_risk   última visita hace 30-60 días
      inactive  última visita hace más de 60 días
    """

    permission_classes = [IsBusinessOwner]
    serializer_class = CustomerSerializer
    search_fields = ["client__first_name", "client__last_name"]
    ordering_fields = ["last_checkin_at", "checkins_count", "lifetime_points", "points_balance"]

    SEGMENTS = ("new", "frequent", "at_risk", "inactive")

    def get_queryset(self):
        qs = (
            Membership.objects.filter(business=self.request.user.business, checkins_count__gt=0)
            .select_related("client")
            .order_by(F("last_checkin_at").desc(nulls_last=True))
        )
        segment = self.request.query_params.get("segment")
        if not segment:
            return qs
        if segment not in self.SEGMENTS:
            raise ValidationError({"segment": f"Usa uno de: {', '.join(self.SEGMENTS)}."})
        return qs.filter(segment_filter(segment, timezone.now()))


def segment_filter(segment: str, now) -> Q:
    d30, d60 = now - timedelta(days=30), now - timedelta(days=60)
    return {
        "new": Q(first_checkin_at__gte=d30),
        "frequent": Q(checkins_count__gte=3, last_checkin_at__gte=d30),
        "at_risk": Q(last_checkin_at__lt=d30, last_checkin_at__gte=d60),
        "inactive": Q(last_checkin_at__lt=d60),
    }[segment]
