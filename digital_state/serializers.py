from rest_framework import serializers

from .models import DayOfWeek, PcUsagePattern


class PcUsagePatternSerializer(serializers.ModelSerializer):
    """조회 응답용."""

    class Meta:
        model = PcUsagePattern
        fields = ["day_of_week", "hour", "is_used"]


class PcUsagePatternItemSerializer(serializers.Serializer):
    """PUT bulk 요청 리스트의 원소 하나를 검증하는 용도(ModelSerializer 아님 — DB에 바로 안 쓰고
    view에서 통째로 delete+bulk_create 하기 때문에 여기선 검증만 담당)."""

    day_of_week = serializers.ChoiceField(choices=DayOfWeek.choices)
    hour = serializers.IntegerField(min_value=0, max_value=23)
    is_used = serializers.BooleanField()
