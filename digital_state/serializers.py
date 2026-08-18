from rest_framework import serializers

from .models import DayOfWeek, PcUsagePattern


class PcUsagePatternSerializer(serializers.ModelSerializer):
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()

    class Meta:
        model = PcUsagePattern
        fields = [
            "id",
            "day_of_week",
            "hour",
            "start_time",
            "end_time",
            "is_used",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "start_time", "end_time", "created_at", "updated_at"]

    def get_start_time(self, obj):
        return f"{obj.hour:02d}:00"

    def get_end_time(self, obj):
        return f"{obj.hour + 1:02d}:00"


class PcUsagePatternInputSerializer(serializers.Serializer):
    day_of_week = serializers.ChoiceField(choices=DayOfWeek.choices)
    hour = serializers.IntegerField(min_value=0, max_value=23)
    is_used = serializers.BooleanField(default=True)


class PcUsagePatternBulkReplaceSerializer(serializers.Serializer):
    patterns = PcUsagePatternInputSerializer(many=True)

    def validate_patterns(self, value):
        seen = set()
        for item in value:
            key = (item["day_of_week"], item["hour"])
            if key in seen:
                raise serializers.ValidationError("같은 요일/시간 조합이 중복되었습니다.")
            seen.add(key)
        return value
