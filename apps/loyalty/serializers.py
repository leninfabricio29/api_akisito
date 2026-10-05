from rest_framework import serializers

from .models import Membership, PointTransaction


class WalletBusinessSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    logo = serializers.ImageField()
    category = serializers.CharField(source="category.name")


class NextRewardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    points_required = serializers.IntegerField()


class WalletSerializer(serializers.ModelSerializer):
    """Monedero del cliente en un negocio."""

    business = WalletBusinessSerializer(read_only=True)
    redeemable_rewards = serializers.IntegerField(read_only=True, default=0)
    next_reward = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "business", "points_balance", "lifetime_points", "checkins_count", "reviews_count",
            "redemptions_count", "first_checkin_at", "last_checkin_at", "redeemable_rewards", "next_reward",
        ]

    def get_next_reward(self, obj):
        reward = getattr(obj, "next_reward_obj", None)
        if not reward:
            return None
        data = NextRewardSerializer(reward).data
        data["points_missing"] = max(reward.points_required - obj.points_balance, 0)
        return data


class PointTransactionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = PointTransaction
        fields = ["id", "kind", "kind_label", "points", "balance_after", "description", "created_at"]


class CustomerSerializer(serializers.ModelSerializer):
    """Cliente visto por el negocio (sin datos sensibles como la cédula)."""

    client = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id", "client", "points_balance", "lifetime_points", "checkins_count", "reviews_count",
            "redemptions_count", "first_checkin_at", "last_checkin_at",
        ]

    def get_client(self, obj):
        request = self.context.get("request")
        avatar = obj.client.avatar.url if obj.client.avatar else None
        return {
            "id": obj.client_id,
            "name": obj.client.get_full_name(),
            "avatar": request.build_absolute_uri(avatar) if (avatar and request and avatar.startswith("/")) else avatar,
        }
