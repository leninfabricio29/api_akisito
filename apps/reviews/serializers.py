from rest_framework import serializers

from .models import Review


class ReviewCreateSerializer(serializers.Serializer):
    checkin_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class PublicReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    avatar = serializers.ImageField(source="client.avatar", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "author", "avatar", "rating", "comment", "reply", "replied_at", "created_at"]

    def get_author(self, obj):
        last = obj.client.last_name[:1]
        return f"{obj.client.first_name} {last}." if last else obj.client.first_name


class MyReviewSerializer(serializers.ModelSerializer):
    business = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "business", "checkin", "rating", "comment", "points_awarded", "status", "reply", "created_at"]

    def get_business(self, obj):
        return {"id": obj.business_id, "name": obj.business.name}


class BusinessReviewSerializer(PublicReviewSerializer):
    class Meta(PublicReviewSerializer.Meta):
        fields = PublicReviewSerializer.Meta.fields + ["status"]


class ReplySerializer(serializers.Serializer):
    reply = serializers.CharField(max_length=1000)
