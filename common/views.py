from rest_framework import generics
from rest_framework.permissions import AllowAny

from common.mixins import EnvelopeMixin

from .models import ActivityTag, StateOption
from .serializers import ActivityTagSerializer, StateOptionSerializer


class ActivityTagListView(EnvelopeMixin, generics.ListAPIView):
    """GET /common/activity-tags/ — 온보딩 활동 태그 카탈로그(읽기 전용, 인증 불필요)."""

    queryset = ActivityTag.objects.filter(is_active=True)
    serializer_class = ActivityTagSerializer
    authentication_classes = []
    permission_classes = [AllowAny]


class StateOptionListView(EnvelopeMixin, generics.ListAPIView):
    """GET /common/state-options/ — 현재 상태 선택지 카탈로그(읽기 전용, 인증 불필요)."""

    queryset = StateOption.objects.filter(is_active=True)
    serializer_class = StateOptionSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
