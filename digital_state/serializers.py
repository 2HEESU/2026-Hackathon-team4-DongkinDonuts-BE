from rest_framework import serializers

from .models import DayOfWeek, PcUsagePattern


class PcUsagePatternSerializer(serializers.ModelSerializer):
    """조회 응답용. hour(정수)만으로는 화면에서 매번 다시 계산해야 해서 start_time/end_time도 같이 내려준다."""

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


class PcUsagePatternItemSerializer(serializers.Serializer):
    """PUT bulk 요청 리스트의 원소 하나를 검증하는 용도(ModelSerializer 아님 — DB에 바로 안 쓰고
    view에서 통째로 delete+bulk_create 하기 때문에 여기선 검증만 담당)."""

    day_of_week = serializers.ChoiceField(choices=DayOfWeek.choices)
    hour = serializers.IntegerField(min_value=0, max_value=23)
    is_used = serializers.BooleanField()
