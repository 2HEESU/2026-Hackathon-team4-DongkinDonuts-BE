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
