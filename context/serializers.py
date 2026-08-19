from rest_framework import serializers

from common.models import ActivityTag, StateOption

from .models import DailyContext, DailyContextActivityTag, DailyContextState, FocusTimeOption
from .utils import today_for_user


def _get_or_create_activity_tags(codes, user):
    """
    activity_tags로 들어온 문자열 목록을 ActivityTag로 매핑한다. 이미 있는 코드(기본
    제공 태그, 또는 이 사용자가 예전에 만든 커스텀 태그)면 그대로 쓰고, 없으면 "+
    직접입력"으로 새로 만든 것으로 보고 created_by=user로 새 ActivityTag를 만든다.
    """
    tags = []
    for code in codes:
        tag, _ = ActivityTag.objects.get_or_create(
            code=code, defaults={"name": code, "created_by": user}
        )
        tags.append(tag)
    return tags

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
    expected_focus_minutes = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1
    )
    tags_skipped = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    activity_tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    # 이슈 #13: state는 더 이상 건너뛸 수 없음 — required=True(기본값) + allow_empty=False라서
    # POST에선 반드시 보내야 하고(partial 아니므로), PATCH에선 아예 안 보내면 건드리지 않지만
    # 보낼 거면 최소 1개는 있어야 한다(빈 리스트로 지우는 것 금지).
    state_options = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    def validate_activity_tags(self, value):
        # 활동 태그는 없는 코드가 오면 커스텀 태그로 자동 생성되므로(get_or_create),
        # 여기서는 같은 값이 중복으로 들어와서 DB의 UniqueConstraint를 건드리는 것만 막는다.
        if len(value) != len(set(value)):
            raise serializers.ValidationError("중복된 활동 태그가 있습니다.")
        return value

    def validate_state_options(self, value):
        # state는 activity_tags와 달리 고정 카탈로그라 자동 생성하지 않는다 — 존재하지 않는
        # 코드가 오면 DB단 FK 에러(500)로 죽기 전에 여기서 깔끔한 400으로 막는다.
        if len(value) != len(set(value)):
            raise serializers.ValidationError("중복된 상태 옵션이 있습니다.")
        existing = set(
            StateOption.objects.filter(code__in=value, is_active=True).values_list("code", flat=True)
        )
        missing = [code for code in value if code not in existing]
        if missing:
            raise serializers.ValidationError(f"존재하지 않는 상태 옵션입니다: {', '.join(missing)}")
        return value

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
        activity_tags = _get_or_create_activity_tags(activity_tag_codes, user)
        DailyContextActivityTag.objects.bulk_create(
            DailyContextActivityTag(daily_context=daily_context, activity_tag=tag)
            for tag in activity_tags
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
            activity_tags = _get_or_create_activity_tags(activity_tag_codes, instance.user)
            DailyContextActivityTag.objects.bulk_create(
                DailyContextActivityTag(daily_context=instance, activity_tag=tag)
                for tag in activity_tags
            )
        if state_codes is not None:
            instance.state_links.all().delete()
            DailyContextState.objects.bulk_create(
                DailyContextState(daily_context=instance, state_id=code, priority=i + 1)
                for i, code in enumerate(state_codes)
            )
        return instance
