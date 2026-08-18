from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.mixins import EnvelopeMixin

from .models import NextActivityPlan, UserContextSnapshot
from .serializers import (
    NextActivityPlanCreateSerializer,
    NextActivityPlanSerializer,
    UserContextSnapshotCreateSerializer,
    UserContextSnapshotSerializer,
)
from .utils import today_for_user


class UserContextSnapshotTodayView(EnvelopeMixin, generics.RetrieveAPIView):
    """GET /context/context-snapshots/today/ — 오늘 등록된 상태 스냅샷 중 최신 1건 조회."""

    serializer_class = UserContextSnapshotSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get_object(self):
        today = today_for_user(self.request.user)
        obj = (
            UserContextSnapshot.objects.filter(user=self.request.user, service_date=today)
            .order_by("-created_at")
            .first()
        )
        if obj is None:
            raise NotFound("오늘 등록된 상태 스냅샷이 없습니다.")
        return obj


class UserContextSnapshotCreateView(EnvelopeMixin, generics.CreateAPIView):
    """POST /context/context-snapshots/ — 지금 내 상태 스냅샷 생성."""

    serializer_class = UserContextSnapshotCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = serializer.save()
        output = UserContextSnapshotSerializer(snapshot)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


class UserContextSnapshotUpdateView(EnvelopeMixin, generics.UpdateAPIView):
    """PATCH /context/context-snapshots/{id}/ — 상태 스냅샷 일부 수정. 본인 것만 수정 가능."""

    serializer_class = UserContextSnapshotCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch", "options"]

    def get_queryset(self):
        return UserContextSnapshot.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        snapshot = serializer.save()
        output = UserContextSnapshotSerializer(snapshot)
        return Response(output.data)


class NextActivityPlanTodayView(EnvelopeMixin, generics.RetrieveAPIView):
    """GET /context/next-activity-plans/today/ — 오늘 등록된 이후 활동 계획 중 최신 1건 조회."""

    serializer_class = NextActivityPlanSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get_object(self):
        today = today_for_user(self.request.user)
        obj = (
            NextActivityPlan.objects.filter(user=self.request.user, service_date=today)
            .order_by("-created_at")
            .first()
        )
        if obj is None:
            raise NotFound("오늘 등록된 이후 활동 계획이 없습니다.")
        return obj


class NextActivityPlanCreateView(EnvelopeMixin, generics.CreateAPIView):
    """POST /context/next-activity-plans/ — 앞으로의 활동 종류와 활동 시간 기록 생성."""

    serializer_class = NextActivityPlanCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        output = NextActivityPlanSerializer(plan)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


class NextActivityPlanUpdateView(EnvelopeMixin, generics.UpdateAPIView):
    """PATCH /context/next-activity-plans/{id}/ — 이후 활동 계획 일부 수정. 본인 것만 수정 가능."""

    serializer_class = NextActivityPlanCreateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch", "options"]

    def get_queryset(self):
        return NextActivityPlan.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        output = NextActivityPlanSerializer(plan)
        return Response(output.data)
