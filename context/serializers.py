from rest_framework import serializers

from common.models import ActivityTag, StateOption

from .models import (
    NextActivityPlan,
    NextActivityPlanActivityTag,
    UserContextSnapshot,
    UserContextSnapshotState,
)
from .services import DEFAULT_STATE_FREQUENCY_DAYS
from .utils import today_for_user


class StateFrequencyQuerySerializer(serializers.Serializer):
    """GET /context/state-frequency/ 쿼리 파라미터(?days=) 검증용."""

    days = serializers.IntegerField(
        required=False, default=DEFAULT_STATE_FREQUENCY_DAYS, min_value=1, max_value=365
    )


def _get_or_create_activity_tags(codes, user):
    """
    activity_tags로 들어온 문자열 목록을 ActivityTag로 매핑한다.
    이미 있는 코드(기본 제공 태그, 또는 이 사용자가 예전에 만든 커스텀 태그)면 그대로 쓰고,
    없으면 "+ 직접입력"으로 새로 만든 것으로 보고 created_by=user로 새 ActivityTag를 만든다.
    """
    tags = []
    for code in codes:
        tag, _ = ActivityTag.objects.get_or_create(
            code=code, defaults={"name": code, "created_by": user}
        )
        tags.append(tag)
    return tags


class UserContextSnapshotSerializer(serializers.ModelSerializer):
    """UserContextSnapshot 조회용. state_options는 우선순위 순서의 코드 목록으로 보여준다."""

    state_options = serializers.SerializerMethodField()

    class Meta:
        model = UserContextSnapshot
        fields = [
            "id",
            "service_date",
            "note",
            "state_options",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "service_date", "created_at", "updated_at"]

    def get_state_options(self, obj):
        return list(obj.state_links.order_by("priority").values_list("state_id", flat=True))


class UserContextSnapshotCreateSerializer(serializers.Serializer):
    """UserContextSnapshot 생성/수정 입력용."""

    note = serializers.CharField(required=False, allow_blank=True, default="")
    # state 정보 없이는 회복 루틴 추천이 성립하지 않으므로 최소 1개 선택을 요구한다.
    state_options = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    def validate_state_options(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("중복된 상태 옵션이 있습니다.")
        existing = set(
            StateOption.objects.filter(code__in=value, is_active=True).values_list("code", flat=True)
        )
        missing = [code for code in value if code not in existing]
        if missing:
            raise serializers.ValidationError(f"존재하지 않는 상태 옵션입니다: {', '.join(missing)}")
        return value

    def create(self, validated_data):
        state_codes = validated_data.pop("state_options")
        user = self.context["request"].user

        snapshot = UserContextSnapshot.objects.create(
            user=user,
            service_date=today_for_user(user),
            **validated_data,
        )
        UserContextSnapshotState.objects.bulk_create(
            UserContextSnapshotState(context_snapshot=snapshot, state_id=code, priority=i + 1)
            for i, code in enumerate(state_codes)
        )
        return snapshot

    def update(self, instance, validated_data):
        state_codes = validated_data.pop("state_options", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if state_codes is not None:
            instance.state_links.all().delete()
            UserContextSnapshotState.objects.bulk_create(
                UserContextSnapshotState(context_snapshot=instance, state_id=code, priority=i + 1)
                for i, code in enumerate(state_codes)
            )
        return instance


class NextActivityPlanSerializer(serializers.ModelSerializer):
    """NextActivityPlan 조회용. activity_tags는 코드 목록으로 보여준다."""

    activity_tags = serializers.SerializerMethodField()

    class Meta:
        model = NextActivityPlan
        fields = [
            "id",
            "context_snapshot",
            "service_date",
            "expected_activity_minutes",
            "activity_tags",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "service_date", "created_at", "updated_at"]

    def get_activity_tags(self, obj):
        return list(obj.activity_tag_links.values_list("activity_tag_id", flat=True))


class NextActivityPlanCreateSerializer(serializers.Serializer):
    """
    NextActivityPlan 생성/수정 입력용.

    expected_activity_minutes가 null이면 이후 활동 시간을 입력하지 않은 것으로 본다.
    """

    context_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=UserContextSnapshot.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    expected_activity_minutes = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1)
    activity_tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate_context_snapshot(self, value):
        if value is not None and value.user_id != self.context["request"].user.id:
            raise serializers.ValidationError("본인의 상태 스냅샷만 연결할 수 있습니다.")
        return value

    def validate_activity_tags(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("중복된 활동 태그가 있습니다.")
        return value

    def create(self, validated_data):
        activity_tag_codes = validated_data.pop("activity_tags")
        user = self.context["request"].user

        plan = NextActivityPlan.objects.create(
            user=user,
            service_date=today_for_user(user),
            **validated_data,
        )
        activity_tags = _get_or_create_activity_tags(activity_tag_codes, user)
        NextActivityPlanActivityTag.objects.bulk_create(
            NextActivityPlanActivityTag(next_activity_plan=plan, activity_tag=tag)
            for tag in activity_tags
        )
        return plan

    def update(self, instance, validated_data):
        activity_tag_codes = validated_data.pop("activity_tags", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if activity_tag_codes is not None:
            instance.activity_tag_links.all().delete()
            activity_tags = _get_or_create_activity_tags(activity_tag_codes, instance.user)
            NextActivityPlanActivityTag.objects.bulk_create(
                NextActivityPlanActivityTag(next_activity_plan=instance, activity_tag=tag)
                for tag in activity_tags
            )
        return instance
