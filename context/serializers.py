from rest_framework import serializers

from .models import (
    NextActivityPlan,
    NextActivityPlanActivityTag,
    UserContextSnapshot,
    UserContextSnapshotState,
)
from .utils import today_for_user


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
    """
    UserContextSnapshot 생성/수정 입력용.

    state_options가 빈 리스트면 사용자가 상태 선택을 하지 않은 것으로 본다. 별도 skipped
    플래그를 저장하지 않아도 null/empty 값만으로 입력 여부를 판단할 수 있다.
    """

    note = serializers.CharField(required=False, allow_blank=True, default="")
    state_options = serializers.ListField(child=serializers.CharField(), required=False, default=list)

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

    def create(self, validated_data):
        activity_tag_codes = validated_data.pop("activity_tags")
        user = self.context["request"].user

        plan = NextActivityPlan.objects.create(
            user=user,
            service_date=today_for_user(user),
            **validated_data,
        )
        NextActivityPlanActivityTag.objects.bulk_create(
            NextActivityPlanActivityTag(next_activity_plan=plan, activity_tag_id=code)
            for code in activity_tag_codes
        )
        return plan

    def update(self, instance, validated_data):
        activity_tag_codes = validated_data.pop("activity_tags", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if activity_tag_codes is not None:
            instance.activity_tag_links.all().delete()
            NextActivityPlanActivityTag.objects.bulk_create(
                NextActivityPlanActivityTag(next_activity_plan=instance, activity_tag_id=code)
                for code in activity_tag_codes
            )
        return instance
