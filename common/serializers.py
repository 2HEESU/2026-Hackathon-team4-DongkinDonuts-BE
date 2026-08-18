from rest_framework import serializers

from .models import ActivityTag, StateOption


class ActivityTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityTag
        fields = ["code", "name", "category"]


class StateOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StateOption
        fields = ["code", "label", "default_difficulty", "routine_direction"]
