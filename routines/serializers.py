from rest_framework import serializers

from .models import ActivityType, RoutineInstance


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

class RoutineInstanceDetailSerializer(serializers.ModelSerializer):
    recovery_slot_id = serializers.UUIDField(read_only=True)
    activity = ActivityTypeSerializer(read_only=True)

    class Meta:
        model = RoutineInstance
        fields = [
            "id",
            "recovery_slot_id",
            "activity",
            "sequence_no",
            "difficulty_level",
            "planned_duration_sec",
            "status",
            "locked_until_previous_done",
            "completed_at",
            "created_at",
            "updated_at",
        ]