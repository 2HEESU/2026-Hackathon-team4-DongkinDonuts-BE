from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from common.mixins import EnvelopeMixin

from .models import ActivityTag, StateOption
from .serializers import ActivityTagSerializer, StateOptionSerializer


class ActivityTagListView(EnvelopeMixin, generics.ListAPIView):
    """
    GET /common/activity-tags/ — 온보딩 활동 태그 카탈로그.
    기본 제공 태그(created_by=null, 전체 공개) + 요청한 본인이 "+ 직접입력"으로
    만든 개인 태그만 보여준다(다른 사용자가 만든 커스텀 태그는 안 보임).
    이 목록을 보려면 사용자 식별이 필요해서(X-Device-Code), state-options와 달리
    인증이 필요하다.
    """

    serializer_class = ActivityTagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ActivityTag.objects.filter(is_active=True).filter(
            Q(created_by__isnull=True) | Q(created_by=self.request.user)
        )


class StateOptionListView(EnvelopeMixin, generics.ListAPIView):
    """GET /common/state-options/ — 현재 상태 선택지 카탈로그(읽기 전용, 인증 불필요, 고정 목록)."""

    queryset = StateOption.objects.filter(is_active=True)
    serializer_class = StateOptionSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
