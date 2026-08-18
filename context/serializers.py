from rest_framework import serializers

from .models import DailyContext, DailyContextActivityTag, DailyContextState, FocusTimeOption
from .utils import today_for_user

FIXED_MINUTES = {
    FocusTimeOption.THIRTY_MINUTES: 30,
    FocusTimeOption.ONE_HOUR: 60,
    FocusTimeOption.TWO_HOURS: 120,
}


class DailyContextSerializer(serializers.ModelSerializer):
    """DailyContext 조회용. activity_tags/state_options는 연결 테이블을 거쳐 코드 목록으로 보여준다."""

    activity_tags = serializers.SerializerMethodField()
    state_options = serializers.SerializerMethodField()

    class Meta:
        model = DailyContext
        fields = [
            "id",
            "service_date",
            "expected_focus_minutes",
            "focus_time_option",
            "state_skipped",
            "tags_skipped",
            "note",
            "activity_tags",
            "state_options",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "service_date", "created_at", "updated_at"]

    def get_activity_tags(self, obj):
        return list(obj.activity_tag_links.values_list("activity_tag_id", flat=True))

    def get_state_options(self, obj):
        return list(obj.state_links.order_by("priority").values_list("state_id", flat=True))


class DailyContextCreateSerializer(serializers.Serializer):
    """
    DailyContext 생성용 입력 전용 시리얼라이저. ModelSerializer가 아니라 plain
    Serializer인 이유: DailyContext 모델 필드만이 아니라 두 개의 연결 테이블
    (DailyContextActivityTag, DailyContextState)까지 한 번에 만들어야 하는
    다중 모델 조합이라, ModelSerializer의 "모델 하나에 1:1 대응" 전제가 안 맞는다.
    """

    focus_time_option = serializers.ChoiceField(choices=FocusTimeOption.choices)
    expected_focus_minutes = serializers.IntegerField(required=False, allow_null=True, default=None)
    state_skipped = serializers.BooleanField(default=False)
    tags_skipped = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    activity_tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    state_options = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate(self, attrs):
        option = attrs.get("focus_time_option")
        if option is None:
            # PATCH(partial=True)에서 이 필드를 아예 안 보낸 경우 — 건드리지 않는다.
            return attrs
        minutes = attrs.get("expected_focus_minutes")

        if option == FocusTimeOption.SKIPPED:
            attrs["expected_focus_minutes"] = None
        elif option in FIXED_MINUTES:
            attrs["expected_focus_minutes"] = FIXED_MINUTES[option]
        elif option == FocusTimeOption.CUSTOM and not minutes:
            raise serializers.ValidationError(
                {"expected_focus_minutes": "focus_time_option이 CUSTOM이면 이 필드가 필요합니다."}
            )
        return attrs

    def create(self, validated_data):
        activity_tag_codes = validated_data.pop("activity_tags")
        state_codes = validated_data.pop("state_options")
        user = self.context["request"].user

        daily_context = DailyContext.objects.create(
            user=user, service_date=today_for_user(user), **validated_data
        )
        DailyContextActivityTag.objects.bulk_create(
            DailyContextActivityTag(daily_context=daily_context, activity_tag_id=code)
            for code in activity_tag_codes
        )
        DailyContextState.objects.bulk_create(
            DailyContextState(daily_context=daily_context, state_id=code, priority=i + 1)
            for i, code in enumerate(state_codes)
        )
        return daily_context

    def update(self, instance, validated_data):
        # None이면 "이 필드는 아예 안 보냄"(안 건드림), 리스트(빈 리스트 포함)면 "전체 교체".
        activity_tag_codes = validated_data.pop("activity_tags", None)
        state_codes = validated_data.pop("state_options", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if activity_tag_codes is not None:
            instance.activity_tag_links.all().delete()
            DailyContextActivityTag.objects.bulk_create(
                DailyContextActivityTag(daily_context=instance, activity_tag_id=code)
                for code in activity_tag_codes
            )
        if state_codes is not None:
            instance.state_links.all().delete()
            DailyContextState.objects.bulk_create(
                DailyContextState(daily_context=instance, state_id=code, priority=i + 1)
                for i, code in enumerate(state_codes)
            )
        return instance
