from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mixins import EnvelopeMixin

from .models import PcUsagePattern
from .serializers import PcUsagePatternBulkReplaceSerializer, PcUsagePatternSerializer
from .services import DAY_ORDER, analyze_pc_usage_patterns


class PcUsagePatternListReplaceView(EnvelopeMixin, APIView):
    """GET/PUT /digital-state/pc-usage-patterns/ — 주간 PC 사용 패턴 조회/전체 교체."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        patterns = sorted(
            PcUsagePattern.objects.filter(user=request.user),
            key=lambda item: (DAY_ORDER.index(item.day_of_week), item.hour),
        )
        return Response(PcUsagePatternSerializer(patterns, many=True).data)

    @transaction.atomic
    def put(self, request):
        serializer = PcUsagePatternBulkReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PcUsagePattern.objects.filter(user=request.user).delete()
        PcUsagePattern.objects.bulk_create(
            PcUsagePattern(
                user=request.user,
                day_of_week=item["day_of_week"],
                hour=item["hour"],
                is_used=item["is_used"],
            )
            for item in serializer.validated_data["patterns"]
        )
        patterns = sorted(
            PcUsagePattern.objects.filter(user=request.user),
            key=lambda item: (DAY_ORDER.index(item.day_of_week), item.hour),
        )
        return Response(PcUsagePatternSerializer(patterns, many=True).data, status=status.HTTP_200_OK)


class PcUsagePatternAnalysisView(EnvelopeMixin, APIView):
    """GET /digital-state/pc-usage-patterns/analysis/ — 주간 PC 사용 패턴 분석 결과 조회."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(analyze_pc_usage_patterns(request.user))
