from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.mixins import EnvelopeMixin

from .models import DailyContext
from .serializers import DailyContextCreateSerializer, DailyContextSerializer
from .utils import today_for_user


class DailyContextTodayView(EnvelopeMixin, generics.RetrieveAPIView):
    """GET /context/daily-contexts/today/ — 오늘 등록된 체크인 중 최신 1건 조회."""

    serializer_class = DailyContextSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get_object(self):
        today = today_for_user(self.request.user)
        obj = (
            DailyContext.objects.filter(user=self.request.user, service_date=today)
            .order_by("-created_at")
            .first()
        )
        if obj is None:
            raise NotFound("오늘 등록된 체크인이 없습니다.")
        return obj


class DailyContextCreateView(EnvelopeMixin, generics.CreateAPIView):
    """POST /context/daily-contexts/ — 오늘의 상황 체크인 생성."""

    serializer_class = DailyContextCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daily_context = serializer.save()
        # 응답은 입력용 시리얼라이저가 아니라 조회용 시리얼라이저로 다시 만든다 —
        # activity_tags/state_options를 연결 테이블에서 다시 읽어와 온전한 모양으로 보여주기 위해.
        output = DailyContextSerializer(daily_context)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


class DailyContextUpdateView(EnvelopeMixin, generics.UpdateAPIView):
    """PATCH /context/daily-contexts/{id}/ — 체크인 일부 수정. 본인 것만 수정 가능."""

    serializer_class = DailyContextCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch", "options"]

    def get_queryset(self):
        return DailyContext.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        daily_context = serializer.save()
        output = DailyContextSerializer(daily_context)
        return Response(output.data)
