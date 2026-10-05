from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.businesses.views import get_approved_business_or_404
from apps.core.permissions import IsBusinessOwner, IsClient

from . import services
from .models import Review
from .serializers import (
    BusinessReviewSerializer,
    MyReviewSerializer,
    PublicReviewSerializer,
    ReplySerializer,
    ReviewCreateSerializer,
)


class MyReviewsView(generics.ListCreateAPIView):
    """GET /reviews/ mis reseñas · POST /reviews/ reseñar una visita."""

    permission_classes = [IsClient]
    serializer_class = MyReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(client=self.request.user).select_related("business")

    def create(self, request, *args, **kwargs):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = services.create_review(request.user, **serializer.validated_data)
        return Response(MyReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class BusinessReviewsView(generics.ListAPIView):
    """GET /businesses/{id}/reviews/ — reseñas públicas y distribución de estrellas."""

    permission_classes = [AllowAny]
    serializer_class = PublicReviewSerializer
    filterset_fields = ["rating"]
    search_fields = []

    def get_queryset(self):
        self.business = get_approved_business_or_404(self.kwargs["business_id"])
        return Review.objects.filter(business=self.business, status=Review.Status.PUBLISHED).select_related("client")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["summary"] = {
            "rating_avg": self.business.rating_avg,
            "rating_count": self.business.rating_count,
            "breakdown": services.rating_breakdown(self.business.pk),
        }
        return response


class OwnBusinessReviewViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /business/reviews/ · POST /business/reviews/{id}/reply/"""

    permission_classes = [IsBusinessOwner]
    serializer_class = BusinessReviewSerializer
    filterset_fields = ["rating"]
    search_fields = ["comment"]

    def get_queryset(self):
        return Review.objects.filter(business=self.request.user.business).select_related("client")

    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        serializer = ReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = services.reply(request.user.business, pk, serializer.validated_data["reply"])
        return Response(BusinessReviewSerializer(review, context={"request": request}).data)
