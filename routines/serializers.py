from rest_framework import serializers

from sessions_app.difficulty import recommended_frontend_difficulty_for_routine

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
    frontend_session_base_id = serializers.SerializerMethodField()
    recommended_difficulty = serializers.SerializerMethodField()
    recommended_difficulty_level = serializers.SerializerMethodField()

    def _recommended_difficulty(self, obj):
        if hasattr(obj, "_recommended_frontend_difficulty"):
            return obj._recommended_frontend_difficulty

        request = self.context.get("request")
        user = getattr(request, "user", None)
        obj._recommended_frontend_difficulty = (
            recommended_frontend_difficulty_for_routine(obj, user=user)
        )
        return obj._recommended_frontend_difficulty

    def get_frontend_session_base_id(self, obj):
        recommended = self._recommended_difficulty(obj)
        return recommended["base_id"] if recommended else None

    def get_recommended_difficulty(self, obj):
        recommended = self._recommended_difficulty(obj)
        return recommended["key"] if recommended else None

    def get_recommended_difficulty_level(self, obj):
        recommended = self._recommended_difficulty(obj)
        return recommended["level"] if recommended else None

    class Meta:
        model = RoutineInstance
        fields = [
            "id",
            "recovery_slot_id",
            "activity",
            "frontend_session_base_id",
            "sequence_no",
            "difficulty_level",
            "recommended_difficulty",
            "recommended_difficulty_level",
            "planned_duration_sec",
            "status",
            "locked_until_previous_done",
            "completed_at",
            "created_at",
            "updated_at",
        ]
