import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.models import ActivityTag, StateOption
from context.models import (
    NextActivityPlan,
    NextActivityPlanActivityTag,
    UserContextSnapshot,
    UserContextSnapshotState,
)
from context.utils import today_for_user
from digital_state.models import PcUsagePattern
from routines.models import (
    ActivityType,
    RoutineInstance,
    RoutineInstanceStatus,
    StageType,
)
from sessions_app.models import (
    DifficultyFeedback,
    RecoveryFeeling,
    Session,
    SessionFeedback,
    SessionStatus,
)

from .models import (
    AIInsight,
    AIPlanRun,
    InsightType,
    Notification,
    NotificationKind,
    NotificationStatus,
    PlanStatus,
    RecoveryPlan,
    RecoverySlot,
    SlotNotificationBasis,
    SlotStatus,
    WebPushSubscription,
)
from .services import (
    build_policy_recommended_slots,
    create_or_replace_today_plan,
    has_today_pc_usage_pattern,
    reset_next_activity_and_slot,
    schedule_next_slot_after_completed_slot,
    set_slot_notification,
    today_day_of_week_for_user,
)
from .web_push import send_due_notifications


class RecoveryPlanServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(id=uuid.uuid4())
        self.state, _ = StateOption.objects.get_or_create(
            code="EYE_TIRED",
            defaults={"label": "눈이 피곤해요"},
        )
        self.activity_tag = ActivityTag.objects.create(code="CODING", name="코딩")
        self.context_snapshot = UserContextSnapshot.objects.create(
            user=self.user,
            service_date=today_for_user(self.user),
        )
        UserContextSnapshotState.objects.create(
            context_snapshot=self.context_snapshot,
            state=self.state,
            priority=1,
        )
        self.next_activity_plan = NextActivityPlan.objects.create(
            user=self.user,
            context_snapshot=self.context_snapshot,
            service_date=today_for_user(self.user),
            expected_activity_minutes=60,
        )
        NextActivityPlanActivityTag.objects.create(
            next_activity_plan=self.next_activity_plan,
            activity_tag=self.activity_tag,
        )

    def test_plan_without_pc_pattern_preserves_snapshot_slots_for_activity_window(self):
        first_time = timezone.now() + timedelta(minutes=60)
        second_time = timezone.now() + timedelta(minutes=120)

        plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_times=[first_time, second_time],
        )

        self.assertEqual(plan.status, PlanStatus.ACTIVE)
        self.assertFalse(plan.generation_snapshot_json["has_today_pc_usage_pattern"])
        self.assertEqual(plan.slots.count(), 2)
        self.assertTrue(
            all(
                slot.notification_basis == SlotNotificationBasis.SNAPSHOT
                for slot in plan.slots.all()
            )
        )

        PcUsagePattern.objects.create(
            user=self.user,
            day_of_week=today_day_of_week_for_user(self.user),
            hour=15,
            is_used=True,
        )
        self.assertTrue(has_today_pc_usage_pattern(self.user))

        second_slot = schedule_next_slot_after_completed_slot(
            completed_slot=plan.slots.order_by("sequence_no").first(),
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_at=second_time,
        )

        self.assertIsNotNone(second_slot)
        self.assertEqual(second_slot.sequence_no, 3)
        self.assertEqual(second_slot.notification_basis, SlotNotificationBasis.SNAPSHOT)
        self.assertEqual(plan.slots.count(), 3)

    def test_policy_slots_split_next_activity_duration_by_state_interval(self):
        fixed_now = timezone.now().replace(hour=13, minute=0, second=0, microsecond=0)
        NextActivityPlan.objects.filter(id=self.next_activity_plan.id).update(
            created_at=fixed_now,
            expected_activity_minutes=120,
        )
        self.next_activity_plan.refresh_from_db()

        slots = build_policy_recommended_slots(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            base_time=fixed_now,
        )

        self.assertEqual(
            [
                slot["recommended_at"]
                for slot in slots
                if slot["notification_basis"] == SlotNotificationBasis.SNAPSHOT
            ],
            [
                fixed_now + timedelta(minutes=20),
                fixed_now + timedelta(minutes=40),
                fixed_now + timedelta(minutes=60),
                fixed_now + timedelta(minutes=80),
                fixed_now + timedelta(minutes=100),
                fixed_now + timedelta(minutes=120),
            ],
        )

    def test_policy_slots_include_previous_session_frequency_times(self):
        fixed_now = timezone.now().replace(hour=13, minute=0, second=0, microsecond=0)
        NextActivityPlan.objects.filter(id=self.next_activity_plan.id).update(
            created_at=fixed_now,
            expected_activity_minutes=60,
        )
        self.next_activity_plan.refresh_from_db()
        plan = RecoveryPlan.objects.create(user=self.user, plan_date=today_for_user(self.user))
        slot = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            sequence_no=1,
            recommended_at=fixed_now + timedelta(minutes=20),
        )
        activity = ActivityType.objects.create(
            code="history_eye_shift",
            stage_type=StageType.BRAIN_SHIFT,
            target_state=self.state,
            name="눈 이완",
            default_duration_sec=90,
        )
        routine = RoutineInstance.objects.create(
            recovery_slot=slot,
            activity=activity,
            sequence_no=1,
            difficulty_level=1,
            planned_duration_sec=90,
        )
        frequent_time = fixed_now.replace(hour=16, minute=30)
        PcUsagePattern.objects.create(
            user=self.user,
            day_of_week=today_day_of_week_for_user(self.user),
            hour=16,
            is_used=True,
        )
        for weeks_ago, minute in enumerate([10, 30, 50], start=1):
            started_at = frequent_time.replace(minute=minute) - timedelta(days=7 * weeks_ago)
            Session.objects.create(
                user=self.user,
                recovery_slot=slot,
                routine_instance=routine,
                activity=activity,
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=2),
                duration_sec=120,
                accuracy=100,
                status=SessionStatus.COMPLETED,
            )

        slots = build_policy_recommended_slots(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            base_time=fixed_now,
        )

        self.assertIn(
            {
                "recommended_at": frequent_time,
                "notification_basis": SlotNotificationBasis.FREQUENCY,
                "reason": "주간 PC 사용 패턴과 최근 회복 세션 기록이 함께 몰린 시간대에 배치했습니다.",
                "data_sources": ["pc_usage_patterns", "previous_sessions", "time_policy"],
            },
            slots,
        )

    def test_plan_with_pc_pattern_does_not_mark_manual_slots_as_frequency(self):
        PcUsagePattern.objects.create(
            user=self.user,
            day_of_week=today_day_of_week_for_user(self.user),
            hour=10,
            is_used=True,
        )
        first_time = timezone.now() + timedelta(minutes=60)
        second_time = timezone.now() + timedelta(minutes=120)

        plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_times=[first_time, second_time],
        )

        self.assertTrue(plan.generation_snapshot_json["has_today_pc_usage_pattern"])
        self.assertEqual(plan.slots.count(), 2)
        self.assertTrue(
            all(
                slot.notification_basis == SlotNotificationBasis.SNAPSHOT
                for slot in plan.slots.all()
            )
        )

        next_slot = schedule_next_slot_after_completed_slot(completed_slot=plan.slots.order_by("sequence_no").first())

        self.assertIsNone(next_slot)
        self.assertEqual(plan.slots.count(), 2)

    def test_notification_setting_is_slot_level_and_defaults_to_enabled(self):
        plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
        )
        slot = plan.slots.get()

        self.assertTrue(slot.notification_enabled)
        self.assertEqual(slot.notifications.filter(status=NotificationStatus.PENDING).count(), 1)

        set_slot_notification(slot=slot, enabled=False, repeat_rule="FREQ=DAILY")
        slot.refresh_from_db()

        self.assertFalse(slot.notification_enabled)
        self.assertEqual(slot.repeat_rule, "")
        self.assertEqual(slot.notifications.filter(status=NotificationStatus.PENDING).count(), 0)
        reengagement = Notification.objects.get(kind=NotificationKind.REENGAGEMENT)
        self.assertIsNone(reengagement.recovery_slot_id)
        self.assertEqual(reengagement.user, self.user)
        self.assertEqual(reengagement.scheduled_at, slot.effective_time + timedelta(days=7))

        set_slot_notification(slot=slot, enabled=True, repeat_rule="FREQ=DAILY")
        slot.refresh_from_db()
        reengagement.refresh_from_db()

        self.assertTrue(slot.notification_enabled)
        self.assertEqual(slot.repeat_rule, "FREQ=DAILY")
        self.assertEqual(slot.notifications.filter(status=NotificationStatus.PENDING).count(), 1)
        self.assertEqual(reengagement.status, NotificationStatus.CANCELED)

    def test_replacing_today_plan_cancels_previous_open_slots_and_notifications(self):
        frequency_time = timezone.now() + timedelta(minutes=70)
        old_plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_slots=[
                {
                    "recommended_at": timezone.now() + timedelta(minutes=60),
                    "notification_basis": SlotNotificationBasis.SNAPSHOT,
                },
                {
                    "recommended_at": frequency_time,
                    "notification_basis": SlotNotificationBasis.FREQUENCY,
                },
            ],
        )
        old_snapshot = old_plan.slots.get(notification_basis=SlotNotificationBasis.SNAPSHOT)
        old_frequency = old_plan.slots.get(notification_basis=SlotNotificationBasis.FREQUENCY)

        new_plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_times=[timezone.now() + timedelta(minutes=90)],
        )

        old_plan.refresh_from_db()
        old_snapshot.refresh_from_db()
        old_frequency.refresh_from_db()
        self.assertEqual(old_plan.status, PlanStatus.REPLACED)
        self.assertEqual(old_snapshot.status, SlotStatus.CANCELED)
        self.assertEqual(old_frequency.status, SlotStatus.CANCELED)
        self.assertEqual(old_snapshot.notifications.filter(status=NotificationStatus.PENDING).count(), 0)
        self.assertEqual(old_frequency.notifications.filter(status=NotificationStatus.PENDING).count(), 0)
        self.assertEqual(new_plan.status, PlanStatus.ACTIVE)
        self.assertTrue(
            new_plan.slots.filter(
                notification_basis=SlotNotificationBasis.FREQUENCY,
                recommended_at=old_frequency.effective_time,
            ).exists()
        )

    @patch("plans.web_push.send_web_push")
    def test_send_due_notifications_sends_pending_notification_to_active_subscriptions(self, mock_send_web_push):
        scheduled_at = timezone.now().replace(microsecond=0)
        notification = Notification.objects.create(
            user=self.user,
            kind=NotificationKind.REENGAGEMENT,
            message="회복 루틴을 다시 시작해볼까요?",
            scheduled_at=scheduled_at,
        )
        subscription = WebPushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.test/subscriptions/worker",
            p256dh="p256dh-key",
            auth="auth-key",
            is_active=True,
        )

        result = send_due_notifications(now=scheduled_at)

        notification.refresh_from_db()
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(result.sent_count, 1)
        self.assertEqual(notification.status, NotificationStatus.SENT)
        self.assertEqual(notification.sent_at, scheduled_at)
        self.assertEqual(mock_send_web_push.call_count, 1)
        sent_subscription, payload = mock_send_web_push.call_args.args
        self.assertEqual(sent_subscription.id, subscription.id)
        self.assertEqual(payload["data"]["notification_id"], str(notification.id))
        self.assertEqual(payload["data"]["kind"], NotificationKind.REENGAGEMENT)

    def test_send_due_notifications_marks_failed_without_active_subscription(self):
        scheduled_at = timezone.now().replace(microsecond=0)
        notification = Notification.objects.create(
            user=self.user,
            kind=NotificationKind.REENGAGEMENT,
            message="회복 루틴을 다시 시작해볼까요?",
            scheduled_at=scheduled_at,
        )

        result = send_due_notifications(now=scheduled_at)

        notification.refresh_from_db()
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(notification.status, NotificationStatus.FAILED)
        self.assertEqual(notification.delivery_error, "활성 Web Push 구독이 없습니다.")

    def test_default_recovery_time_uses_shortest_state_policy_interval(self):
        body_state, _ = StateOption.objects.get_or_create(
            code="BODY_STIFF",
            defaults={"label": "몸이 굳었어요"},
        )
        UserContextSnapshotState.objects.create(
            context_snapshot=self.context_snapshot,
            state=body_state,
            priority=2,
        )
        fixed_now = timezone.now().replace(hour=13, minute=0, second=0, microsecond=0)

        with patch("plans.services.timezone.now", return_value=fixed_now):
            plan = create_or_replace_today_plan(
                user=self.user,
                context_snapshot=self.context_snapshot,
                next_activity_plan=self.next_activity_plan,
            )

        slot = plan.slots.get()
        self.assertEqual(slot.recommended_at, fixed_now + timedelta(minutes=20))
        self.assertEqual(slot.interval_minutes, 20)
        self.assertEqual(plan.generation_snapshot_json["time_policy"]["interval_minutes"], 20)
        self.assertEqual(
            plan.generation_snapshot_json["time_policy"]["selected_state_codes"],
            ["EYE_TIRED"],
        )

    def test_reset_next_activity_replaces_open_snapshot_slots_and_keeps_frequency(self):
        fixed_now = timezone.now().replace(hour=13, minute=0, second=0, microsecond=0)
        plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_slots=[
                {
                    "recommended_at": fixed_now + timedelta(minutes=20),
                    "notification_basis": SlotNotificationBasis.SNAPSHOT,
                },
                {
                    "recommended_at": fixed_now + timedelta(minutes=30),
                    "notification_basis": SlotNotificationBasis.FREQUENCY,
                },
                {
                    "recommended_at": fixed_now + timedelta(minutes=40),
                    "notification_basis": SlotNotificationBasis.SNAPSHOT,
                },
            ],
        )
        target_slot = plan.slots.filter(notification_basis=SlotNotificationBasis.SNAPSHOT).order_by("sequence_no").first()
        frequency_slot = plan.slots.get(notification_basis=SlotNotificationBasis.FREQUENCY)
        replacement_activity_plan = NextActivityPlan.objects.create(
            user=self.user,
            context_snapshot=self.context_snapshot,
            service_date=today_for_user(self.user),
            expected_activity_minutes=60,
        )
        NextActivityPlan.objects.filter(id=replacement_activity_plan.id).update(created_at=fixed_now)
        replacement_activity_plan.refresh_from_db()

        with patch("plans.services.timezone.now", return_value=fixed_now):
            replacement_slot = reset_next_activity_and_slot(
                user=self.user,
                target_slot=target_slot,
                context_snapshot=self.context_snapshot,
                next_activity_plan=replacement_activity_plan,
            )

        old_snapshot_statuses = list(
            plan.slots.filter(
                notification_basis=SlotNotificationBasis.SNAPSHOT,
                next_activity_plan=self.next_activity_plan,
            ).values_list("status", flat=True)
        )
        replacement_snapshot_times = list(
            plan.slots.filter(
                notification_basis=SlotNotificationBasis.SNAPSHOT,
                next_activity_plan=replacement_activity_plan,
                status__in=[SlotStatus.RECOMMENDED, SlotStatus.SCHEDULED, SlotStatus.CHANGED],
            )
            .order_by("recommended_at")
            .values_list("recommended_at", flat=True)
        )
        frequency_slot.refresh_from_db()

        self.assertTrue(all(status == SlotStatus.CANCELED for status in old_snapshot_statuses))
        self.assertEqual(frequency_slot.status, SlotStatus.RECOMMENDED)
        self.assertEqual(replacement_slot.sequence_no, 4)
        self.assertEqual(replacement_slot.next_activity_plan_id, replacement_activity_plan.id)
        self.assertEqual(
            replacement_snapshot_times,
            [
                fixed_now + timedelta(minutes=20),
                fixed_now + timedelta(minutes=40),
                fixed_now + timedelta(minutes=60),
            ],
        )
        self.assertEqual(
            plan.slots.filter(
                status__in=[SlotStatus.RECOMMENDED, SlotStatus.SCHEDULED, SlotStatus.CHANGED],
            ).count(),
            4,
        )


class RecoveryPlanApiTests(APITestCase):
    def setUp(self):
        self.device_code = uuid.uuid4()
        self.client.credentials(HTTP_X_DEVICE_CODE=str(self.device_code))
        self.state = StateOption.objects.create(code="NECK_STIFF", label="목이 뻐근해요")
        self.activity_tag = ActivityTag.objects.create(code="ASSIGNMENT", name="과제")

    def test_create_today_plan_from_context_snapshot_and_next_activity_plan(self):
        snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [self.state.code]},
            format="json",
        )
        activity_plan_response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 45,
            },
            format="json",
        )

        response = self.client.post(
            "/api/v1/plans/recovery-plans/today/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "next_activity_plan": activity_plan_response.data["data"]["id"],
                "recommended_times": [(timezone.now() + timedelta(minutes=45)).isoformat()],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertFalse(response.data["data"]["generation_snapshot_json"]["has_today_pc_usage_pattern"])
        self.assertEqual(len(response.data["data"]["slots"]), 1)
        self.assertTrue(response.data["data"]["slots"][0]["notification_enabled"])

    def test_recovery_slot_detail_next_feedback_and_notification_endpoints(self):
        snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [self.state.code]},
            format="json",
        )
        activity_plan_response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 45,
            },
            format="json",
        )
        self.client.post(
            "/api/v1/plans/recovery-plans/today/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "next_activity_plan": activity_plan_response.data["data"]["id"],
                "recommended_times": [(timezone.now() + timedelta(minutes=45)).isoformat()],
            },
            format="json",
        )

        next_response = self.client.get("/api/v1/plans/recovery-slots/next/")
        slot_id = next_response.data["data"]["id"]

        detail_response = self.client.get(f"/api/v1/plans/recovery-slots/{slot_id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["data"]["id"], slot_id)

        reset_time_response = self.client.get("/api/v1/plans/recovery-slots/next-reset-time/")
        self.assertEqual(reset_time_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reset_time_response.data["data"]["recovery_slot"], slot_id)

        RecoverySlot.objects.filter(id=slot_id).update(status=SlotStatus.STARTED)
        future_slot = RecoverySlot.objects.create(
            recovery_plan_id=detail_response.data["data"]["recovery_plan"],
            sequence_no=2,
            recommended_at=timezone.now() + timedelta(minutes=90),
        )

        runnable_response = self.client.get("/api/v1/plans/recovery-slots/next/")
        reset_time_response = self.client.get("/api/v1/plans/recovery-slots/next-reset-time/")

        self.assertEqual(runnable_response.status_code, status.HTTP_200_OK)
        self.assertEqual(runnable_response.data["data"]["id"], slot_id)
        self.assertEqual(reset_time_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reset_time_response.data["data"]["recovery_slot"], str(future_slot.id))

        notification_response = self.client.patch(
            f"/api/v1/plans/recovery-slots/{slot_id}/notification/",
            {"notification_enabled": True, "repeat_rule": "FREQ=DAILY"},
            format="json",
        )
        self.assertEqual(notification_response.status_code, status.HTTP_200_OK)
        self.assertTrue(notification_response.data["data"]["notification_enabled"])

        notifications_response = self.client.get("/api/v1/plans/notifications/")
        notification_id = notifications_response.data["data"][0]["id"]
        click_response = self.client.post(f"/api/v1/plans/notifications/{notification_id}/click/")
        self.assertEqual(click_response.status_code, status.HTTP_200_OK)
        self.assertEqual(click_response.data["data"]["status"], NotificationStatus.CLICKED)

        feedback_response = self.client.post(
            f"/api/v1/plans/recovery-slots/{slot_id}/feedback/",
            {
                "recovery_feeling": "MUCH_BETTER",
                "difficulty_feedback": "JUST_RIGHT",
            },
            format="json",
        )
        self.assertEqual(feedback_response.status_code, status.HTTP_201_CREATED)

        history_response = self.client.get("/api/v1/plans/recovery-slots/history/")
        self.assertEqual(history_response.status_code, status.HTTP_200_OK)
        self.assertEqual(history_response.data["data"][0]["id"], slot_id)

    def test_ai_generate_uses_fixed_wake_shift_groups_and_reset(self):
        eye_state, _ = StateOption.objects.get_or_create(
            code="EYE_TIRED",
            defaults={"label": "눈이 피로해요"},
        )
        snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [eye_state.code]},
            format="json",
        )
        activity_plan_response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 40,
            },
            format="json",
        )
        fixed_now = timezone.now().replace(hour=13, minute=0, second=0, microsecond=0)
        NextActivityPlan.objects.filter(id=activity_plan_response.data["data"]["id"]).update(
            created_at=fixed_now,
        )

        with patch("plans.ai_planner.timezone.now", return_value=fixed_now):
            response = self.client.post(
                "/api/v1/plans/recovery-plans/today/ai-generate/",
                {
                    "context_snapshot": snapshot_response.data["data"]["id"],
                    "next_activity_plan": activity_plan_response.data["data"]["id"],
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first_slot = response.data["data"]["slots"][0]
        self.assertEqual(
            [routine["activity"]["code"] for routine in first_slot["routine_instances"]],
            [
                "WAKE_HAND_ROUTINE",
                "SHIFT_EYE_RELAX",
                "SHIFT_EYE_TRACKING",
                "RESET_BREATH",
            ],
        )
        body_state, _ = StateOption.objects.get_or_create(
            code="BODY_STIFF",
            defaults={"label": "목과 어깨가 굳었어요"},
        )
        body_snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [body_state.code]},
            format="json",
        )
        body_activity_plan_response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": body_snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 30,
            },
            format="json",
        )
        NextActivityPlan.objects.filter(id=body_activity_plan_response.data["data"]["id"]).update(
            created_at=fixed_now,
        )

        with patch("plans.ai_planner.timezone.now", return_value=fixed_now):
            body_response = self.client.post(
                "/api/v1/plans/recovery-plans/today/ai-generate/",
                {
                    "context_snapshot": body_snapshot_response.data["data"]["id"],
                    "next_activity_plan": body_activity_plan_response.data["data"]["id"],
                },
                format="json",
            )

        self.assertEqual(body_response.status_code, status.HTTP_201_CREATED)
        body_first_slot = body_response.data["data"]["slots"][0]
        self.assertEqual(
            [routine["activity"]["code"] for routine in body_first_slot["routine_instances"]],
            [
                "WAKE_HAND_ROUTINE",
                "SHIFT_BODY_STRETCH",
                "SHIFT_SHOULDER_PMR",
                "RESET_BREATH",
            ],
        )

    def test_cancel_before_keeps_frequency_and_selected_time_slots(self):
        user = User.objects.create(id=self.device_code, timezone="Asia/Seoul")
        snapshot = UserContextSnapshot.objects.create(user=user, service_date=today_for_user(user))
        UserContextSnapshotState.objects.create(context_snapshot=snapshot, state=self.state, priority=1)
        activity_plan = NextActivityPlan.objects.create(
            user=user,
            context_snapshot=snapshot,
            service_date=today_for_user(user),
            expected_activity_minutes=90,
        )
        plan = RecoveryPlan.objects.create(user=user, plan_date=today_for_user(user))
        now = timezone.now().replace(microsecond=0)
        selected_time = now + timedelta(minutes=40)

        snapshot_before = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=1,
            recommended_at=now + timedelta(minutes=20),
            notification_basis=SlotNotificationBasis.SNAPSHOT,
        )
        frequency_before = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=2,
            recommended_at=now + timedelta(minutes=25),
            notification_basis=SlotNotificationBasis.FREQUENCY,
        )
        selected_slot = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=3,
            recommended_at=selected_time,
            notification_basis=SlotNotificationBasis.SNAPSHOT,
        )
        snapshot_after = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=4,
            recommended_at=now + timedelta(minutes=80),
            notification_basis=SlotNotificationBasis.SNAPSHOT,
        )

        response = self.client.post(
            "/api/v1/plans/recovery-slots/cancel-before/",
            {
                "before": selected_time.isoformat(),
                "exclude_slot": str(selected_slot.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["canceled_count"], 1)
        snapshot_before.refresh_from_db()
        frequency_before.refresh_from_db()
        selected_slot.refresh_from_db()
        snapshot_after.refresh_from_db()
        self.assertEqual(snapshot_before.status, SlotStatus.CANCELED)
        self.assertEqual(frequency_before.status, SlotStatus.RECOMMENDED)
        self.assertEqual(selected_slot.status, SlotStatus.RECOMMENDED)
        self.assertEqual(snapshot_after.status, SlotStatus.RECOMMENDED)

    def test_reentry_consumes_only_nearest_future_snapshot_slot(self):
        user = User.objects.create(id=self.device_code, timezone="Asia/Seoul")
        plan = RecoveryPlan.objects.create(user=user, plan_date=today_for_user(user))
        now = timezone.now().replace(microsecond=0)
        frequency_first = RecoverySlot.objects.create(
            recovery_plan=plan,
            sequence_no=1,
            recommended_at=now + timedelta(minutes=5),
            notification_basis=SlotNotificationBasis.FREQUENCY,
        )
        first_snapshot = RecoverySlot.objects.create(
            recovery_plan=plan,
            sequence_no=2,
            recommended_at=now + timedelta(minutes=10),
            notification_basis=SlotNotificationBasis.SNAPSHOT,
        )
        second_snapshot = RecoverySlot.objects.create(
            recovery_plan=plan,
            sequence_no=3,
            recommended_at=now + timedelta(minutes=20),
            notification_basis=SlotNotificationBasis.SNAPSHOT,
        )

        response = self.client.post("/api/v1/plans/recovery-slots/consume-nearest-snapshot/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["canceled_count"], 1)
        frequency_first.refresh_from_db()
        first_snapshot.refresh_from_db()
        second_snapshot.refresh_from_db()
        self.assertEqual(frequency_first.status, SlotStatus.RECOMMENDED)
        self.assertEqual(first_snapshot.status, SlotStatus.CANCELED)
        self.assertEqual(second_snapshot.status, SlotStatus.RECOMMENDED)

    def test_history_supports_date_filters_and_table_fields(self):
        snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [self.state.code], "note": "오전 내내 모니터를 봄"},
            format="json",
        )
        activity_plan_response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 45,
            },
            format="json",
        )
        user = User.objects.get(id=self.device_code)
        snapshot = UserContextSnapshot.objects.get(id=snapshot_response.data["data"]["id"])
        activity_plan = NextActivityPlan.objects.get(id=activity_plan_response.data["data"]["id"])
        today = today_for_user(user)
        tomorrow = today + timedelta(days=1)
        now = timezone.now().replace(microsecond=0)

        plan = RecoveryPlan.objects.create(
            user=user,
            plan_date=today,
            generation_snapshot_json={
                "service_date": str(today),
                "has_today_pc_usage_pattern": True,
                "has_pc_usage_pattern": True,
                "pc_usage_pattern_count": 1,
                "pc_usage_patterns": [{"day_of_week": today_day_of_week_for_user(user), "hour": 9, "is_used": True}],
                "context_snapshot": {"id": str(snapshot.id)},
                "next_activity_plan": {"id": str(activity_plan.id)},
            },
        )
        missed_slot = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=1,
            recommended_at=now - timedelta(minutes=30),
            status=SlotStatus.RECOMMENDED,
        )
        completed_slot = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=2,
            recommended_at=now - timedelta(minutes=90),
            status=SlotStatus.COMPLETED,
        )
        upcoming_slot = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=3,
            recommended_at=now + timedelta(minutes=60),
            status=SlotStatus.RECOMMENDED,
        )
        tomorrow_plan = RecoveryPlan.objects.create(
            user=user,
            plan_date=tomorrow,
            generation_snapshot_json={"service_date": str(tomorrow)},
        )
        RecoverySlot.objects.create(
            recovery_plan=tomorrow_plan,
            sequence_no=1,
            recommended_at=now + timedelta(days=1),
        )

        activity = ActivityType.objects.create(
            code="history_neck_shift",
            stage_type=StageType.BRAIN_SHIFT,
            target_state=self.state,
            name="목 이완",
            default_duration_sec=90,
        )
        routine = RoutineInstance.objects.create(
            recovery_slot=missed_slot,
            activity=activity,
            sequence_no=1,
            difficulty_level=2,
            planned_duration_sec=90,
        )
        AIInsight.objects.create(
            recovery_plan=plan,
            recovery_slot=missed_slot,
            insight_type=InsightType.RECOMMENDATION_REASON,
            body="연속 사용 전에 짧은 휴식이 필요합니다.",
            data_sources_json=["context_snapshot", "next_activity_plan", "pc_usage_patterns"],
        )
        AIInsight.objects.create(
            recovery_plan=plan,
            recovery_slot=missed_slot,
            routine_instance=routine,
            insight_type=InsightType.ROUTINE_REASON,
            body="목 긴장을 낮추기 위한 루틴입니다.",
            data_sources_json=["llm_routine_reason"],
        )

        SessionFeedback.objects.create(
            recovery_slot=completed_slot,
            user=user,
            recovery_feeling="MUCH_BETTER",
            difficulty_feedback="JUST_RIGHT",
            skipped=False,
        )

        date_response = self.client.get(f"/api/v1/plans/recovery-slots/history/?date={today}")
        self.assertEqual(date_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(date_response.data["data"]), 3)

        history_statuses = {item["id"]: item["history_status"] for item in date_response.data["data"]}
        self.assertEqual(history_statuses[str(missed_slot.id)], "UPCOMING")
        self.assertEqual(history_statuses[str(completed_slot.id)], "COMPLETED")
        self.assertEqual(history_statuses[str(upcoming_slot.id)], "UPCOMING")

        completed_item = next(item for item in date_response.data["data"] if item["id"] == str(completed_slot.id))
        self.assertEqual(completed_item["remark"], "훨씬 나아졌어요")

        missed_item = next(item for item in date_response.data["data"] if item["id"] == str(missed_slot.id))
        self.assertEqual(missed_item["history_status_label"], "진행 예정")

        self.assertIn("목이 뻐근해요", missed_item["input_summary"])
        self.assertIn("과제", missed_item["input_summary"])
        self.assertIn("45분 예정", missed_item["input_summary"])
        self.assertEqual(missed_item["recommended_routines"][0]["activity"]["code"], "history_neck_shift")
        self.assertEqual(missed_item["recommended_routines"][0]["reason"], "목 긴장을 낮추기 위한 루틴입니다.")
        self.assertEqual(missed_item["remark"], "brainfit의 추천 시간")
        self.assertIn("디지털 사용 패턴", missed_item["data_source_summary"]["labels"])
        self.assertIn("디지털 사용 패턴", missed_item["data_notice"])

        range_response = self.client.get(
            f"/api/v1/plans/recovery-slots/history/?from_date={today}&to_date={today}"
        )
        self.assertEqual(range_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(range_response.data["data"]), 3)

        invalid_range_response = self.client.get(
            f"/api/v1/plans/recovery-slots/history/?start_date={tomorrow}&end_date={today}"
        )
        self.assertEqual(invalid_range_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_history_marks_unanswered_sent_notification_as_canceled_after_grace_period(self):
        user = User.objects.create(id=self.device_code, timezone="Asia/Seoul")
        snapshot = UserContextSnapshot.objects.create(user=user, service_date=today_for_user(user))
        UserContextSnapshotState.objects.create(context_snapshot=snapshot, state=self.state, priority=1)
        activity_plan = NextActivityPlan.objects.create(
            user=user,
            context_snapshot=snapshot,
            service_date=today_for_user(user),
            expected_activity_minutes=45,
        )
        plan = RecoveryPlan.objects.create(user=user, plan_date=today_for_user(user))
        sent_at = timezone.now().replace(microsecond=0) - timedelta(minutes=11)
        slot = RecoverySlot.objects.create(
            recovery_plan=plan,
            context_snapshot=snapshot,
            next_activity_plan=activity_plan,
            sequence_no=1,
            recommended_at=sent_at,
            notification_basis=SlotNotificationBasis.SNAPSHOT,
        )
        Notification.objects.create(
            user=user,
            recovery_slot=slot,
            kind=NotificationKind.RECOVERY_SLOT,
            message="회복 세션을 시작할 시간입니다.",
            scheduled_at=sent_at,
            sent_at=sent_at,
            status=NotificationStatus.SENT,
        )

        response = self.client.get(f"/api/v1/plans/recovery-slots/history/?date={today_for_user(user)}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slot.refresh_from_db()
        self.assertEqual(slot.status, SlotStatus.CANCELED)
        item = response.data["data"][0]
        self.assertEqual(item["history_status"], "CANCELED")
        self.assertEqual(item["history_status_label"], "취소")

    def test_ai_generate_creates_plan_slots_routines_and_logs(self):
        snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [self.state.code], "note": "잠을 적게 잠"},
            format="json",
        )
        activity_plan_response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 90,
            },
            format="json",
        )
        user = User.objects.get(id=self.device_code)
        today_day = today_day_of_week_for_user(user)
        PcUsagePattern.objects.create(user=user, day_of_week=today_day, hour=14, is_used=True)
        PcUsagePattern.objects.create(user=user, day_of_week=today_day, hour=15, is_used=True)
        fixed_now = timezone.now().replace(hour=13, minute=0, second=0, microsecond=0)
        NextActivityPlan.objects.filter(id=activity_plan_response.data["data"]["id"]).update(
            created_at=fixed_now,
        )

        shift = ActivityType.objects.create(
            code="shift_neck",
            stage_type=StageType.BRAIN_SHIFT,
            target_state=self.state,
            name="목 이완",
            default_duration_sec=90,
        )
        second_shift = ActivityType.objects.create(
            code="shift_neck_focus",
            stage_type=StageType.BRAIN_SHIFT,
            target_state=self.state,
            name="목 이완 후 집중 전환",
            default_duration_sec=60,
        )
        ActivityType.objects.filter(
            target_state=self.state,
            stage_type=StageType.BRAIN_SHIFT,
        ).exclude(
            code__in=[shift.code, second_shift.code],
        ).update(is_active=False)
        with patch("plans.ai_planner.timezone.now", return_value=fixed_now):
            response = self.client.post(
                "/api/v1/plans/recovery-plans/today/ai-generate/",
                {
                    "context_snapshot": snapshot_response.data["data"]["id"],
                    "next_activity_plan": activity_plan_response.data["data"]["id"],
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertIsNotNone(response.data["data"]["ai_plan_run"])
        self.assertEqual(len(response.data["data"]["slots"]), 2)
        self.assertEqual(response.data["data"]["slots"][0]["interval_minutes"], 45)
        for slot in response.data["data"]["slots"]:
            stage_types = [routine["stage_type"] for routine in slot["routine_instances"]]
            self.assertEqual(stage_types[0], StageType.BRAIN_WAKE)
            self.assertEqual(stage_types[-1], StageType.BRAIN_RESET)
            self.assertEqual(len(slot["routine_instances"]), 4)
            self.assertEqual(stage_types.count(StageType.BRAIN_SHIFT), 2)
            self.assertEqual(
                slot["notification_basis"],
                SlotNotificationBasis.SNAPSHOT,
            )
            self.assertEqual(slot["routine_instances"][0]["activity"]["code"], "WAKE_HAND_ROUTINE")
            self.assertEqual(slot["routine_instances"][-1]["activity"]["code"], "RESET_BREATH")

        first_slot_routines = response.data["data"]["slots"][0]["routine_instances"]
        second_slot_routines = response.data["data"]["slots"][1]["routine_instances"]
        self.assertEqual(first_slot_routines[0]["activity"]["code"], second_slot_routines[0]["activity"]["code"])
        self.assertEqual(first_slot_routines[1]["activity"]["code"], shift.code)
        self.assertEqual(first_slot_routines[2]["activity"]["code"], second_shift.code)
        self.assertEqual(second_slot_routines[1]["activity"]["code"], shift.code)
        self.assertEqual(first_slot_routines[3]["stage_type"], StageType.BRAIN_RESET)
        self.assertEqual(second_slot_routines[3]["stage_type"], StageType.BRAIN_RESET)
        self.assertEqual(AIPlanRun.objects.count(), 1)
        ai_run = AIPlanRun.objects.get()
        self.assertEqual(ai_run.model_name, "server_policy")
        self.assertFalse(ai_run.output_snapshot_json["raw_response"]["external_api_called"])
        self.assertEqual(
            [activity["code"] for activity in ai_run.input_snapshot_json["shift_activity_catalog"]],
            [shift.code, second_shift.code],
        )
        self.assertEqual(ai_run.input_snapshot_json["time_policy"]["interval_minutes"], 45)
        self.assertEqual(AIInsight.objects.count(), 8)
        self.assertEqual(RoutineInstance.objects.count(), 8)
        created_slots = list(
            RecoverySlot.objects.filter(
                recovery_plan_id=response.data["data"]["id"],
            ).order_by("sequence_no")
        )
        self.assertEqual(
            [slot.recommended_at for slot in created_slots],
            [
                fixed_now.replace(hour=13, minute=45),
                fixed_now.replace(hour=14, minute=30),
            ],
        )

        today_slots_response = self.client.get("/api/v1/plans/recovery-slots/today/")
        self.assertEqual(today_slots_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(today_slots_response.data["data"]), 2)

    def test_web_push_subscription_create_list_and_delete(self):
        with override_settings(WEB_PUSH_VAPID_PUBLIC_KEY="public-key"):
            key_response = self.client.get("/api/v1/plans/notification-subscriptions/vapid-public-key/")
        self.assertEqual(key_response.status_code, status.HTTP_200_OK)
        self.assertEqual(key_response.data["data"]["public_key"], "public-key")

        create_response = self.client.post(
            "/api/v1/plans/notification-subscriptions/",
            {
                "endpoint": "https://push.example.test/subscriptions/abc",
                "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
                "user_agent": "test-browser",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        subscription_id = create_response.data["data"]["id"]
        self.assertEqual(WebPushSubscription.objects.count(), 1)

        list_response = self.client.get("/api/v1/plans/notification-subscriptions/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data["data"]), 1)

        delete_response = self.client.delete(f"/api/v1/plans/notification-subscriptions/{subscription_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(delete_response.data["data"]["is_active"])

        list_after_delete_response = self.client.get("/api/v1/plans/notification-subscriptions/")
        self.assertEqual(list_after_delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_after_delete_response.data["data"], [])


class RecoverySlotRoutineDifficultyApiTests(APITestCase):
    def setUp(self):
        self.device_code = uuid.uuid4()
        self.user = User.objects.create(id=self.device_code, timezone="Asia/Seoul")
        self.client.credentials(HTTP_X_DEVICE_CODE=str(self.device_code))
        self.plan = RecoveryPlan.objects.create(
            user=self.user,
            plan_date=today_for_user(self.user),
        )
        self.activity, _ = ActivityType.objects.update_or_create(
            code="SHIFT_EYE_RELAX",
            defaults={
                "stage_type": StageType.BRAIN_SHIFT,
                "name": "눈 피로 풀기",
                "purpose": "화면 사용으로 긴장된 눈과 시선을 쉬게 합니다.",
                "required_landmarks": ["LEFT_EYE", "RIGHT_EYE"],
                "min_difficulty": 1,
                "max_difficulty": 4,
                "default_duration_sec": 90,
                "is_active": True,
            },
        )

    def _create_slot_with_routine(self, sequence_no, status=SlotStatus.RECOMMENDED):
        slot = RecoverySlot.objects.create(
            recovery_plan=self.plan,
            sequence_no=sequence_no,
            recommended_at=timezone.now() + timedelta(minutes=sequence_no * 20),
            status=status,
        )
        routine = RoutineInstance.objects.create(
            recovery_slot=slot,
            activity=self.activity,
            sequence_no=1,
            difficulty_level=2,
            planned_duration_sec=90,
            status=RoutineInstanceStatus.AVAILABLE,
            locked_until_previous_done=False,
        )
        return slot, routine

    def test_routine_defaults_to_medium_without_previous_feedback(self):
        slot, _ = self._create_slot_with_routine(sequence_no=1)

        response = self.client.get(f"/api/v1/plans/recovery-slots/{slot.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        routine_data = response.data["data"]["routine_instances"][0]
        self.assertEqual(routine_data["frontend_session_base_id"], "eye-blink")
        self.assertEqual(routine_data["recommended_difficulty"], "medium")
        self.assertEqual(routine_data["recommended_difficulty_level"], 2)

    def test_routine_uses_previous_completed_session_feedback(self):
        previous_slot, previous_routine = self._create_slot_with_routine(
            sequence_no=1,
            status=SlotStatus.COMPLETED,
        )
        started_at = timezone.now() - timedelta(days=1, minutes=3)
        Session.objects.create(
            user=self.user,
            recovery_slot=previous_slot,
            routine_instance=previous_routine,
            activity=self.activity,
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=2),
            duration_sec=120,
            accuracy=95,
            metrics={"difficulty": "medium"},
            status=SessionStatus.COMPLETED,
        )
        SessionFeedback.objects.create(
            recovery_slot=previous_slot,
            user=self.user,
            recovery_feeling=RecoveryFeeling.SAME,
            difficulty_feedback=DifficultyFeedback.TOO_EASY,
        )
        current_slot, _ = self._create_slot_with_routine(sequence_no=2)

        response = self.client.get(f"/api/v1/plans/recovery-slots/{current_slot.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        routine_data = response.data["data"]["routine_instances"][0]
        self.assertEqual(routine_data["recommended_difficulty"], "high")
        self.assertEqual(routine_data["recommended_difficulty_level"], 3)
