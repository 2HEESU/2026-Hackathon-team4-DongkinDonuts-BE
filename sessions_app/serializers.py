from rest_framework import serializers

from common.constants import CameraPermissionStatus
from routines.models import RoutineInstanceStatus
from routines.serializers import ActivityTypeSerializer

from .models import Session, SessionEvent, DifficultyFeedback, RecoveryFeeling, SessionFeedback

class SessionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionEvent
        fields = [
            "id",
            "event_type",
            "step_no",
            "message",
            "created_at",
        ]

class SessionSerializer(serializers.ModelSerializer):
    recovery_slot_id = serializers.UUIDField(read_only=True)
    routine_instance_id = serializers.UUIDField(read_only=True)
    activity = ActivityTypeSerializer(read_only=True)
    events = SessionEventSerializer(many=True, read_only=True)
    remaining_session_count = serializers.SerializerMethodField()

    def get_remaining_session_count(self, obj):
        routine_instances = getattr(
            obj.recovery_slot,
            "_prefetched_objects_cache",
            {},
        ).get("routine_instances")

        terminal_statuses = {
            RoutineInstanceStatus.COMPLETED,
            RoutineInstanceStatus.CANCELED,
        }

        if routine_instances is not None:
            return sum(
                routine_instance.status not in terminal_statuses
                for routine_instance in routine_instances
            )

        return (
            obj.recovery_slot.routine_instances.exclude(
                status__in=terminal_statuses,
            )
            .count()
        )

    class Meta:
        model = Session
        fields = [
            "id",
            "recovery_slot_id",
            "routine_instance_id",
            "remaining_session_count",
            "activity",
            "started_at",
            "ended_at",
            "duration_sec",
            "accuracy",
            "metrics",
            "status",
            "camera_permission_status",
            "reset_count",
            "events",
            "created_at",
            "updated_at",
        ]

class SessionStartSerializer(serializers.Serializer):
    routine_instance_id = serializers.UUIDField()
    camera_permission_status = serializers.ChoiceField(
        choices=CameraPermissionStatus.choices,
    )

class SessionCompleteSerializer(serializers.Serializer):
    accuracy = serializers.IntegerField(
        min_value=0,
        max_value=100,
    )
    metrics = serializers.JSONField(
        required=False,
        allow_null=True,
    )

class SessionEventCreateSerializer(serializers.Serializer):
    event_type = serializers.CharField(max_length=50)
    step_no = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=4,
        error_messages={
            "min_value": "step_no는 1~4 사이의 숫자여야 합니다.",
            "max_value": "step_no는 1~4 사이의 숫자여야 합니다.",
        },
    )
    message = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )

class SessionFeedbackSerializer(serializers.ModelSerializer):
    recovery_slot_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SessionFeedback
        fields = [
            "id",
            "recovery_slot_id",
            "recovery_feeling",
            "difficulty_feedback",
            "skipped",
            "created_at",
            "updated_at",
        ]

class SessionFeedbackCreateSerializer(serializers.Serializer):
    recovery_slot_id = serializers.UUIDField()
    recovery_feeling = serializers.ChoiceField(
        choices=RecoveryFeeling.choices,
        required=False,
        allow_null=True
    )
    difficulty_feedback = serializers.ChoiceField(
        choices=DifficultyFeedback.choices,
        required=False,
        allow_null=True,
    )
    skipped = serializers.BooleanField(default=False)
