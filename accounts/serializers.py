from zoneinfo import available_timezones

from rest_framework import serializers

from .models import User, UserSettings


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "nickname", "timezone", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_timezone(self, value):
        # 검증 없이 통과시키면, 이후 context.utils.today_for_user()의 ZoneInfo(user.timezone)
        # 호출이 전부 500으로 죽는다(존재하지 않는 timezone 문자열이면). 여기서 미리 막는다.
        if value not in available_timezones():
            raise serializers.ValidationError(
                '올바른 IANA timezone이 아닙니다 (예: "Asia/Seoul").'
            )
        return value


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["id", "notification_enabled", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
