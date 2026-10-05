from django.utils import timezone
from rest_framework import serializers

from .models import CheckIn


class ScanSerializer(serializers.Serializer):
    qr = serializers.CharField(max_length=255, help_text="Contenido leído del QR (akisito://checkin/<token>).")
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    accuracy = serializers.FloatField(min_value=0, required=False, allow_null=True, help_text="Precisión GPS en metros.")
    is_mocked = serializers.BooleanField(required=False, default=False)


class CheckInBusinessSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    logo = serializers.ImageField()


class CheckInSerializer(serializers.ModelSerializer):
    business = CheckInBusinessSerializer(read_only=True)
    has_review = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    review_points = serializers.SerializerMethodField()

    class Meta:
        model = CheckIn
        fields = [
            "id", "business", "points_awarded", "created_at", "review_deadline", "has_review", "can_review",
            "review_points",
        ]

    def get_has_review(self, obj):
        return hasattr(obj, "review")

    def get_can_review(self, obj):
        return not hasattr(obj, "review") and obj.review_window_open(timezone.now())

    def get_review_points(self, obj):
        """Puntos que daría reseñar esta visita ahora (0 si ya no se puede o ya ganó puntos en el periodo)."""
        from .services import pending_review_points

        if not self.get_can_review(obj):
            return 0
        return pending_review_points(obj.client, obj.business)


def scan_response(result, request) -> dict:
    checkin, membership, business = result.checkin, result.membership, result.checkin.business
    return {
        "checkin": {"id": checkin.pk, "created_at": checkin.created_at},
        "business": CheckInBusinessSerializer(business, context={"request": request}).data,
        "points_earned": checkin.points_awarded,
        "balance": membership.points_balance,
        "visits": membership.checkins_count,
        "review": {
            "available": True,
            "points": result.review_points,
            "deadline": checkin.review_deadline,
        },
    }
