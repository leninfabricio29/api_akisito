from django.utils import timezone
from rest_framework import serializers

from .models import Redemption, Reward


class RewardSerializer(serializers.ModelSerializer):
    """Recompensa vista por el cliente."""

    business = serializers.SerializerMethodField()
    my_points = serializers.IntegerField(read_only=True, default=None)
    can_redeem = serializers.SerializerMethodField()
    stock_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reward
        fields = [
            "id", "business", "title", "description", "image", "points_required", "starts_at", "ends_at",
            "max_per_client", "stock_left", "my_points", "can_redeem",
        ]

    def get_business(self, obj):
        logo = obj.business.logo.url if obj.business.logo else None
        return {"id": obj.business_id, "name": obj.business.name, "logo": logo}

    def get_can_redeem(self, obj):
        my_points = getattr(obj, "my_points", None)
        return my_points is not None and my_points >= obj.points_required


class OwnRewardSerializer(serializers.ModelSerializer):
    """Recompensa gestionada por el negocio."""

    stock_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reward
        fields = [
            "id", "title", "description", "image", "points_required", "starts_at", "ends_at",
            "max_per_client", "stock", "stock_left", "redeemed_count", "is_active", "created_at",
        ]
        read_only_fields = ["id", "redeemed_count", "created_at"]

    def validate(self, attrs):
        instance = self.instance
        starts_at = attrs.get("starts_at", instance.starts_at if instance else timezone.now())
        ends_at = attrs.get("ends_at", instance.ends_at if instance else None)
        if ends_at and starts_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "La fecha de fin debe ser posterior a la de inicio."})
        if instance and "stock" in attrs and attrs["stock"] is not None and attrs["stock"] < instance.redeemed_count:
            raise serializers.ValidationError(
                {"stock": f"Ya hay {instance.redeemed_count} canjes; el stock no puede ser menor."}
            )
        if instance and "points_required" in attrs and attrs["points_required"] != instance.points_required:
            if instance.redemptions.filter(status=Redemption.Status.PENDING).exists():
                raise serializers.ValidationError(
                    {"points_required": "Hay canjes pendientes: no puedes cambiar el precio hasta que se validen."}
                )
        return attrs


class RedemptionSerializer(serializers.ModelSerializer):
    reward = serializers.SerializerMethodField()
    business = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Redemption
        fields = [
            "id", "code", "reward", "business", "points_spent", "status", "status_label",
            "expires_at", "validated_at", "created_at",
        ]

    def get_reward(self, obj):
        image = obj.reward.image.url if obj.reward.image else None
        return {"id": obj.reward_id, "title": obj.reward.title, "image": image}

    def get_business(self, obj):
        return {"id": obj.business_id, "name": obj.business.name}


class BusinessRedemptionSerializer(RedemptionSerializer):
    client = serializers.SerializerMethodField()

    class Meta(RedemptionSerializer.Meta):
        fields = RedemptionSerializer.Meta.fields + ["client"]

    def get_client(self, obj):
        return {"id": obj.client_id, "name": obj.client.get_full_name()}


class ValidateCodeSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=4, max_length=16)
