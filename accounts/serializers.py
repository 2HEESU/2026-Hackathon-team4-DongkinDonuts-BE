from rest_framework import serializers

from .models import User, UserSettings


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "nickname", "timezone", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["id", "notification_enabled", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
