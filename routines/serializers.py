from rest_framework import serializers

from .models import ActivityType


class ActivityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = [
            "code",
            "stage_type",
            "target_state",
            "name",
            "purpose",
            "required_landmarks",
            "min_difficulty",
            "max_difficulty",
            "default_duration_sec",
        ]