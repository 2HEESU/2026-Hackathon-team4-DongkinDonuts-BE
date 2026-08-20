from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mixins import EnvelopeMixin

from .models import DayOfWeek, PcUsagePattern
from .serializers import PcUsagePatternItemSerializer, PcUsagePatternSerializer
from .services import analyze_pc_usage_patterns, analyze_recent_session_patterns, get_pattern_status

# day_of_week가 문자열(CharField)이라 그냥 정렬하면 월~일 순서가 안 나옴 —
# 화면에 보여줄 순서를 여기서 직접 정의해서 정렬 키로 쓴다.
DAY_ORDER = {code: i for i, code in enumerate(DayOfWeek.values)}


def ordered_patterns(user):
    patterns = PcUsagePattern.objects.filter(user=user)
    return sorted(patterns, key=lambda p: (DAY_ORDER[p.day_of_week], p.hour))


class PcUsagePatternBulkUpdateView(EnvelopeMixin, APIView):
    """
    PUT /digital-state/patterns/bulk/ — 일주일 PC 사용 패턴 전체 교체.
    generics 제네릭 뷰에 맞는 동작(단건 조회/생성/수정)이 아니라 "리스트 통째로 교체"라서
    APIView를 직접 써서 로직을 짠다.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["put", "options"]

    def put(self, request, *args, **kwargs):
        item_serializer = PcUsagePatternItemSerializer(data=request.data, many=True)
        item_serializer.is_valid(raise_exception=True)
        items = item_serializer.validated_data

        seen = set()
        for item in items:
            key = (item["day_of_week"], item["hour"])
            if key in seen:
                raise ValidationError(f"{item['day_of_week']} {item['hour']}시가 중복 입력되었습니다.")
            seen.add(key)

        with transaction.atomic():
            PcUsagePattern.objects.filter(user=request.user).delete()
            PcUsagePattern.objects.bulk_create(
                PcUsagePattern(user=request.user, **item) for item in items
            )

        output = PcUsagePatternSerializer(ordered_patterns(request.user), many=True)
        return Response(output.data)


class PcUsagePatternListView(EnvelopeMixin, generics.ListAPIView):
    """
    GET /digital-state/patterns/ — 이번 유저의 PC 사용 패턴 전체 조회(최대 168개).
    DELETE /digital-state/patterns/ — 전체 초기화.
    같은 주소(/patterns/)를 GET/DELETE 둘 다 써서, 별도 클래스로 안 쪼개고 한 클래스에
    .delete()를 추가했다 — urls.py에 같은 path()를 두 번 못 쓰기 때문(먼저 매칭된 것만 실행됨).
    """

    serializer_class = PcUsagePatternSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get_queryset(self):
        # order_by는 QuerySet 상태를 유지해야 하니, 파이썬 정렬(ordered_patterns) 대신
        # Case/When으로 day_of_week 문자열을 정수 순서로 매핑해서 DB 단에서 정렬한다.
        day_order = Case(
            *[When(day_of_week=day, then=Value(i)) for day, i in DAY_ORDER.items()],
            output_field=IntegerField(),
        )
        return (
            PcUsagePattern.objects.filter(user=self.request.user)
            .annotate(day_order=day_order)
            .order_by("day_order", "hour")
        )

    def delete(self, request, *args, **kwargs):
        PcUsagePattern.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PcUsagePatternAnalysisView(EnvelopeMixin, APIView):
    """
    GET /digital-state/patterns/analysis/ — 주간 PC 사용 패턴 분석 결과 조회(AI 미사용).
    저장된 요일×시간 체크값을 그대로 집계해서 연속 사용 구간/최다 사용 요일·시간대를 계산한다.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    def get(self, request, *args, **kwargs):
        return Response(analyze_pc_usage_patterns(request.user))


class RecentSessionActivityAnalysisView(EnvelopeMixin, APIView):
    """
    GET /digital-state/patterns/analysis/recent-sessions/ — 지난 7일간 실제로
    완료한 회복 세션 기록 기반 분석. PcUsagePatternAnalysisView(자기보고 체크값
    기반)와 응답 형태는 동일하고, 데이터 출처만 실제 행동 기록으로 바뀐다 —
    사용자가 "이 시간에 쓸 것 같다"고 미리 체크해둔 예정보다, 실제로 회복
    세션을 시작한 시점이 더 신뢰할 수 있는 신호라서 이쪽을 우선한다.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    def get(self, request, *args, **kwargs):
        return Response(analyze_recent_session_patterns(request.user, days=7))


class PcUsagePatternStatusView(EnvelopeMixin, APIView):
    """
    GET /digital-state/patterns/status/ — PC 사용 패턴 맞춤 설정 여부 판별(가벼운 플래그).
    온보딩 질문 분기, AI 하루치 일정 vs 단건 추천 분기 등에서 매번 전체 목록을 받아
    직접 계산하지 않아도 되게 서버가 미리 판단해서 내려준다.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    def get(self, request, *args, **kwargs):
        return Response(get_pattern_status(request.user))
