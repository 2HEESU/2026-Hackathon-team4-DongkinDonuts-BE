from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mixins import EnvelopeMixin
from context.utils import today_for_user

from .ai_planner import generate_ai_recovery_plan
from .models import Notification, PlanStatus, RecoveryPlan, RecoverySlot, WebPushSubscription
from .serializers import (
    AIRecoveryPlanGenerateSerializer,
    NotificationSerializer,
    RecoverySlotCancelBeforeSerializer,
    RecoveryPlanCreateSerializer,
    RecoveryPlanSerializer,
    RecoverySlotCreateSerializer,
    RecoverySlotHistoryQuerySerializer,
    RecoverySlotHistorySerializer,
    RecoverySlotNotificationSerializer,
    RecoverySlotScheduleSerializer,
    RecoverySlotSerializer,
    SlotFeedbackSerializer,
    SlotFeedbackSubmitSerializer,
    WebPushSubscriptionCreateSerializer,
    WebPushSubscriptionSerializer,
)
from .services import (
    cancel_next_snapshot_slot_for_reentry,
    cancel_snapshot_slots_before,
    cancel_slot,
    cleanup_nearby_pattern_notifications_on_entry,
    create_or_replace_today_plan,
    create_recovery_slot,
    deactivate_web_push_subscription,
    expire_unanswered_recovery_slots,
    get_next_slot_for_user,
    get_runnable_slot_for_user,
    mark_notification_clicked,
    notification_user_filter,
    reset_next_activity_and_slot,
    schedule_slot_time,
    set_slot_notification,
    submit_slot_feedback,
    upsert_web_push_subscription,
)


class RecoveryPlanTodayView(EnvelopeMixin, APIView):
    """GET/POST /plans/recovery-plans/today/ — 오늘 active plan 조회 또는 재생성."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        plan = (
            RecoveryPlan.objects.select_related("ai_plan_run")
            .prefetch_related(
                "insights",
                "slots__insights",
                "slots__routine_instances__activity",
                "slots__routine_instances__insights",
                "slots__notifications",
            )
            .filter(user=request.user, plan_date=today_for_user(request.user), status=PlanStatus.ACTIVE)
            .first()
        )
        if plan is None:
            raise NotFound("오늘 활성 회복 계획이 없습니다.")
        return Response(RecoveryPlanSerializer(plan).data)

    def post(self, request):
        serializer = RecoveryPlanCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        plan = create_or_replace_today_plan(user=request.user, **serializer.validated_data)
        return Response(RecoveryPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class RecoveryPlanTodayAIGenerateView(EnvelopeMixin, APIView):
    """
    POST /plans/recovery-plans/today/ai-generate/ — 오늘 회복 계획 생성.
    use_ai_decision=true일 때만 실제 LLM을 시도하고, 아니면(기본값) 서버 정책
    엔진만 쓴다.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AIRecoveryPlanGenerateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        plan = generate_ai_recovery_plan(user=request.user, **serializer.validated_data)
        return Response(RecoveryPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class RecoveryPlanTodayNextSlotView(EnvelopeMixin, APIView):
    """POST /plans/recovery-plans/today/next-slot/ — 오늘 active plan에 다음 슬롯 1개 추가."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RecoverySlotCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        plan = get_object_or_404(
            RecoveryPlan,
            user=request.user,
            plan_date=today_for_user(request.user),
            status=PlanStatus.ACTIVE,
        )
        slot = create_recovery_slot(plan=plan, **serializer.validated_data)
        return Response(RecoverySlotSerializer(slot).data, status=status.HTTP_201_CREATED)


class RecoveryPlanResetNextActivityView(EnvelopeMixin, APIView):
    """POST /plans/recovery-plans/today/reset-next-activity/ — 가장 가까운 열린 슬롯 하나를 재생성."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RecoverySlotCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        slot = reset_next_activity_and_slot(user=request.user, **serializer.validated_data)
        return Response(RecoverySlotSerializer(slot).data, status=status.HTTP_201_CREATED)


class RecoverySlotResetNextActivityView(EnvelopeMixin, APIView):
    """POST /plans/recovery-slots/{id}/reset-next-activity/ — 지정 슬롯을 새 이후 활동 계획으로 대체."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        target_slot = get_object_or_404(RecoverySlot, pk=pk, recovery_plan__user=request.user)
        serializer = RecoverySlotCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        slot = reset_next_activity_and_slot(
            user=request.user,
            target_slot=target_slot,
            **serializer.validated_data,
        )
        return Response(RecoverySlotSerializer(slot).data, status=status.HTTP_201_CREATED)


class RecoverySlotListView(EnvelopeMixin, generics.ListAPIView):
    """GET /plans/recovery-slots/ — 내 회복 슬롯 전체 목록."""

    serializer_class = RecoverySlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        expire_unanswered_recovery_slots(user=self.request.user)
        return (
            RecoverySlot.objects.select_related("recovery_plan", "recovery_plan__ai_plan_run")
            .prefetch_related(
                "insights",
                "notifications",
                "routine_instances__activity",
                "routine_instances__insights",
            )
            .filter(recovery_plan__user=self.request.user)
            .order_by("-recovery_plan__plan_date", "sequence_no")
        )


class RecoverySlotTodayListView(EnvelopeMixin, generics.ListAPIView):
    """GET /plans/recovery-slots/today/ — 오늘 active plan의 회복 슬롯 목록."""

    serializer_class = RecoverySlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        expire_unanswered_recovery_slots(user=self.request.user)
        # 사용자가 오늘 슬롯 목록을 조회하는 시점 = 서비스에 진입한 시점으로 보고,
        # 지금과 너무 가까운 시간대의 빈도 기반 알림은 이미 사용자가 들어와있으니
        # 굳이 다시 알릴 필요 없다고 판단해 취소한다.
        cleanup_nearby_pattern_notifications_on_entry(user=self.request.user)
        return (
            RecoverySlot.objects.select_related("recovery_plan", "recovery_plan__ai_plan_run")
            .prefetch_related(
                "insights",
                "notifications",
                "routine_instances__activity",
                "routine_instances__insights",
            )
            .filter(
                recovery_plan__user=self.request.user,
                recovery_plan__plan_date=today_for_user(self.request.user),
                recovery_plan__status=PlanStatus.ACTIVE,
            )
            .order_by("sequence_no")
        )


class RecoverySlotHistoryView(EnvelopeMixin, generics.ListAPIView):
    """GET /plans/recovery-slots/history/ — 기간별 회복 슬롯 기록 목록."""

    serializer_class = RecoverySlotHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["now"] = timezone.now()
        return context

    def get_history_filters(self):
        query_params = self.request.query_params.copy()
        if "from_date" in query_params and "start_date" not in query_params:
            query_params["start_date"] = query_params["from_date"]
        if "to_date" in query_params and "end_date" not in query_params:
            query_params["end_date"] = query_params["to_date"]

        serializer = RecoverySlotHistoryQuerySerializer(data=query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def get_queryset(self):
        filters = self.get_history_filters()
        expire_unanswered_recovery_slots(user=self.request.user)
        queryset = (
            RecoverySlot.objects.select_related(
                "recovery_plan",
                "recovery_plan__ai_plan_run",
                "context_snapshot",
                "next_activity_plan",
            )
            .prefetch_related(
                "insights",
                "notifications",
                "routine_instances__activity",
                "routine_instances__insights",
                "context_snapshot__state_links__state",
                "next_activity_plan__activity_tag_links__activity_tag",
                "recovery_plan__insights",
            )
            .filter(recovery_plan__user=self.request.user)
        )

        if filters.get("date"):
            queryset = queryset.filter(recovery_plan__plan_date=filters["date"])
        else:
            if filters.get("start_date"):
                queryset = queryset.filter(recovery_plan__plan_date__gte=filters["start_date"])
            if filters.get("end_date"):
                queryset = queryset.filter(recovery_plan__plan_date__lte=filters["end_date"])

        # 화면에는 effective_time(user_changed_at → scheduled_at → recommended_at 순
        # 우선순위, RecoverySlot.effective_time 프로퍼티와 동일한 로직)을 보여주는데,
        # 정렬은 recommended_at만 보고 있었다. "시간 변경하기"로 시각을 바꾼 슬롯이
        # 있으면 화면에 보이는 시간과 실제 정렬 순서가 어긋나서 표가 뒤죽박죽으로
        # 보이는 버그가 있었다 — 같은 우선순위로 annotate해서 그걸로 정렬한다.
        queryset = queryset.annotate(
            effective_time_sort=Coalesce("user_changed_at", "scheduled_at", "recommended_at")
        )

        return queryset.order_by(
            "-recovery_plan__plan_date",
            "effective_time_sort",
            "created_at",
        )


class RecoverySlotDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    """GET /plans/recovery-slots/{id}/ — 회복 슬롯 상세 조회."""

    serializer_class = RecoverySlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            RecoverySlot.objects.select_related(
                "recovery_plan",
                "recovery_plan__ai_plan_run",
                "context_snapshot",
                "next_activity_plan",
            )
            .prefetch_related(
                "insights",
                "notifications",
                "routine_instances__activity",
                "routine_instances__insights",
            )
            .filter(recovery_plan__user=self.request.user)
        )


class RecoverySlotNextView(EnvelopeMixin, APIView):
    """GET /plans/recovery-slots/next/ — 현재 가장 먼저 수행할 회복 슬롯 상세 조회."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        slot = get_runnable_slot_for_user(request.user)
        if slot is None:
            raise NotFound("다음 회복 슬롯이 없습니다.")
        return Response(RecoverySlotSerializer(slot).data)


class RecoverySlotNextResetTimeView(EnvelopeMixin, APIView):
    """GET /plans/recovery-slots/next-reset-time/ — 다음 리셋 시간 조회."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        slot = get_next_slot_for_user(request.user)
        if slot is None:
            raise NotFound("다음 리셋 시간이 없습니다.")
        effective_time = slot.effective_time
        return Response(
            {
                "recovery_slot": str(slot.id),
                "next_reset_time": effective_time,
                "is_overdue": effective_time < timezone.now(),
            }
        )


class RecoverySlotScheduleView(EnvelopeMixin, APIView):
    """PATCH /plans/recovery-slots/{id}/schedule/ — 슬롯 시간 변경."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        slot = get_object_or_404(RecoverySlot, pk=pk, recovery_plan__user=request.user)
        serializer = RecoverySlotScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slot = schedule_slot_time(slot=slot, **serializer.validated_data)
        return Response(RecoverySlotSerializer(slot).data)


class RecoverySlotCancelBeforeView(EnvelopeMixin, APIView):
    """POST /plans/recovery-slots/cancel-before/ — 지정 시각 이전 스냅샷 기반 슬롯을 취소."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RecoverySlotCancelBeforeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        slots = cancel_snapshot_slots_before(user=request.user, **serializer.validated_data)
        return Response(
            {
                "canceled_count": len(slots),
                "slots": RecoverySlotSerializer(slots, many=True).data,
            }
        )


class RecoverySlotConsumeSnapshotView(EnvelopeMixin, APIView):
    """POST /plans/recovery-slots/consume-nearest-snapshot/ — 재진입으로 가장 가까운 스냅샷 슬롯 1개 취소."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        slot = cancel_next_snapshot_slot_for_reentry(user=request.user)
        return Response(
            {
                "canceled_count": 1 if slot else 0,
                "slot": RecoverySlotSerializer(slot).data if slot else None,
            }
        )


class RecoverySlotNotificationView(EnvelopeMixin, APIView):
    """PATCH /plans/recovery-slots/{id}/notification/ — 슬롯 웹 알림 설정."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        slot = get_object_or_404(RecoverySlot, pk=pk, recovery_plan__user=request.user)
        serializer = RecoverySlotNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slot = set_slot_notification(
            slot=slot,
            enabled=serializer.validated_data["notification_enabled"],
            repeat_rule=serializer.validated_data["repeat_rule"],
        )
        return Response(RecoverySlotSerializer(slot).data)


class RecoverySlotCancelView(EnvelopeMixin, APIView):
    """POST /plans/recovery-slots/{id}/cancel/ — 슬롯 취소."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        slot = get_object_or_404(RecoverySlot, pk=pk, recovery_plan__user=request.user)
        slot = cancel_slot(slot=slot)
        return Response(RecoverySlotSerializer(slot).data)


class RecoverySlotFeedbackView(EnvelopeMixin, APIView):
    """POST /plans/recovery-slots/{id}/feedback/ — 수행한 회복 슬롯 피드백 제출."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        slot = get_object_or_404(RecoverySlot, pk=pk, recovery_plan__user=request.user)
        serializer = SlotFeedbackSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = submit_slot_feedback(slot=slot, **serializer.validated_data)
        return Response(SlotFeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


class NotificationListView(EnvelopeMixin, generics.ListAPIView):
    """GET /plans/notifications/ — 내 회복 슬롯 웹 알림 발신 목록."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Notification.objects.select_related("user", "recovery_slot", "recovery_slot__recovery_plan")
            .filter(notification_user_filter(self.request.user))
            .order_by("-scheduled_at", "-created_at")
        )
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset


class NotificationClickView(EnvelopeMixin, APIView):
    """POST /plans/notifications/{id}/click/ — 웹 알림 클릭 처리."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(
            Notification.objects.filter(notification_user_filter(request.user)),
            pk=pk,
        )
        notification = mark_notification_clicked(notification=notification)
        return Response(NotificationSerializer(notification).data)


class WebPushVapidPublicKeyView(EnvelopeMixin, APIView):
    """GET /plans/notification-subscriptions/vapid-public-key/ — PushManager 구독용 VAPID 공개키."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"public_key": settings.WEB_PUSH_VAPID_PUBLIC_KEY})


class WebPushSubscriptionListCreateView(EnvelopeMixin, APIView):
    """GET/POST /plans/notification-subscriptions/ — 브라우저 Web Push 구독 조회/등록."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscriptions = WebPushSubscription.objects.filter(user=request.user, is_active=True)
        return Response(WebPushSubscriptionSerializer(subscriptions, many=True).data)

    def post(self, request):
        serializer = WebPushSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        keys = serializer.validated_data["keys"]
        subscription = upsert_web_push_subscription(
            user=request.user,
            endpoint=serializer.validated_data["endpoint"],
            p256dh=keys["p256dh"],
            auth=keys["auth"],
            user_agent=serializer.validated_data["user_agent"],
        )
        return Response(WebPushSubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)


class WebPushSubscriptionDeleteView(EnvelopeMixin, APIView):
    """DELETE /plans/notification-subscriptions/{id}/ — Web Push 구독 비활성화."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        subscription = get_object_or_404(WebPushSubscription, pk=pk, user=request.user)
        subscription = deactivate_web_push_subscription(subscription=subscription)
        return Response(WebPushSubscriptionSerializer(subscription).data)
