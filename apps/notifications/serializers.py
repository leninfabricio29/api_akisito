from rest_framework import serializers

from .models import Device, Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "data", "is_read", "read_at", "created_at"]

    def get_is_read(self, obj):
        return obj.read_at is not None


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["token", "platform", "name"]
        extra_kwargs = {"token": {"validators": []}}  # el token se reasigna, no se rechaza por duplicado


class DeviceTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=255)
