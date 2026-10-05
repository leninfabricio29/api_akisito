from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core.validators import validate_ruc
from apps.loyalty.services import checkin_points_for, checkin_radius_for, review_points_for

from .models import Business, Category, Favorite


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "icon"]


class BusinessCreateSerializer(serializers.Serializer):
    """Alta del negocio desde la app, después de crear la cuenta con el correo."""

    name = serializers.CharField(max_length=120)
    ruc = serializers.CharField(max_length=13)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True))
    address = serializers.CharField(max_length=255)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_ruc(self, value):
        try:
            info = validate_ruc(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if Business.objects.filter(ruc=info.number).exists():
            raise serializers.ValidationError("Este RUC ya está registrado.")
        return info.number


class BusinessListSerializer(serializers.ModelSerializer):
    """Tarjeta de negocio para listados públicos."""

    category = CategorySerializer(read_only=True)
    distance_m = serializers.SerializerMethodField()
    is_favorite = serializers.BooleanField(read_only=True, default=False)
    my_points = serializers.IntegerField(read_only=True, default=None)
    checkin_points = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id", "name", "category", "logo", "cover", "address", "latitude", "longitude",
            "rating_avg", "rating_count", "checkin_points", "distance_m", "is_favorite", "my_points",
        ]

    def get_distance_m(self, obj):
        distance = getattr(obj, "distance_m", None)
        return round(distance) if distance is not None else None

    def get_checkin_points(self, obj):
        return checkin_points_for(obj, self.context.get("loyalty_settings"))


class BusinessDetailSerializer(BusinessListSerializer):
    review_points = serializers.SerializerMethodField()

    class Meta(BusinessListSerializer.Meta):
        fields = BusinessListSerializer.Meta.fields + ["description", "review_points"]

    def get_review_points(self, obj):
        return review_points_for(obj, self.context.get("loyalty_settings"))


class OwnBusinessSerializer(serializers.ModelSerializer):
    """Perfil del negocio visto y editado por su propietario."""

    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True))
    effective_rules = serializers.SerializerMethodField()
    location_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Business
        fields = [
            "id", "name", "ruc", "taxpayer_type", "category", "description", "logo", "cover",
            "address", "latitude", "longitude", "location_locked",
            "status", "status_reason", "checkin_points", "review_points", "checkin_radius_m",
            "effective_rules", "rating_avg", "rating_count", "created_at",
        ]
        read_only_fields = [
            "id", "ruc", "taxpayer_type", "status", "status_reason", "rating_avg", "rating_count", "created_at",
        ]

    def validate(self, attrs):
        moved = any(key in attrs and attrs[key] != getattr(self.instance, key) for key in ("latitude", "longitude"))
        if self.instance and self.instance.location_locked and moved:
            raise serializers.ValidationError(
                {"latitude": "Tu negocio ya fue aprobado: para cambiar la ubicación contacta a soporte."}
            )
        return attrs

    def get_effective_rules(self, obj):
        return {
            "checkin_points": checkin_points_for(obj),
            "review_points": review_points_for(obj),
            "checkin_radius_m": checkin_radius_for(obj),
        }


class FavoriteSerializer(serializers.ModelSerializer):
    business = BusinessListSerializer(read_only=True)
    business_id = serializers.PrimaryKeyRelatedField(
        source="business", queryset=Business.objects.approved(), write_only=True
    )

    class Meta:
        model = Favorite
        fields = ["id", "business", "business_id", "created_at"]
        read_only_fields = ["id", "created_at"]
