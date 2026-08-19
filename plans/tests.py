import json
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
from routines.models import ActivityType, RoutineInstance, StageType

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
    SlotStatus,
    WebPushSubscription,
)
from .services import (
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

    def test_plan_without_pc_pattern_creates_one_slot_per_call_and_keeps_snapshot_branch(self):
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
        self.assertEqual(plan.slots.count(), 1)

        PcUsagePattern.objects.create(
            user=self.user,
            day_of_week=today_day_of_week_for_user(self.user),
            hour=15,
            is_used=True,
        )
        self.assertTrue(has_today_pc_usage_pattern(self.user))

        second_slot = schedule_next_slot_after_completed_slot(
            completed_slot=plan.slots.get(),
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_at=second_time,
        )

        self.assertIsNotNone(second_slot)
        self.assertEqual(second_slot.sequence_no, 2)
        self.assertEqual(plan.slots.count(), 2)

    def test_plan_with_pc_pattern_creates_all_recommended_slots_and_does_not_append_after_completion(self):
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

    def test_reset_next_activity_replaces_only_one_slot_in_a_multi_slot_day(self):
        PcUsagePattern.objects.create(
            user=self.user,
            day_of_week=today_day_of_week_for_user(self.user),
            hour=10,
            is_used=True,
        )
        recommended_times = [
            timezone.now() + timedelta(minutes=60),
            timezone.now() + timedelta(minutes=120),
            timezone.now() + timedelta(minutes=180),
        ]
        plan = create_or_replace_today_plan(
            user=self.user,
            context_snapshot=self.context_snapshot,
            next_activity_plan=self.next_activity_plan,
            recommended_times=recommended_times,
        )
        target_slot = plan.slots.order_by("sequence_no")[1]
        replacement_activity_plan = NextActivityPlan.objects.create(
            user=self.user,
            context_snapshot=self.context_snapshot,
            service_date=today_for_user(self.user),
            expected_activity_minutes=30,
        )

        replacement_slot = reset_next_activity_and_slot(
            user=self.user,
            target_slot=target_slot,
            context_snapshot=self.context_snapshot,
            next_activity_plan=replacement_activity_plan,
            recommended_at=timezone.now() + timedelta(minutes=90),
        )

        target_slot.refresh_from_db()
        untouched_slots = plan.slots.exclude(id__in=[target_slot.id, replacement_slot.id])

        self.assertEqual(target_slot.status, SlotStatus.CANCELED)
        self.assertEqual(replacement_slot.sequence_no, 4)
        self.assertEqual(replacement_slot.next_activity_plan_id, replacement_activity_plan.id)
        self.assertEqual(plan.slots.filter(status__in=[SlotStatus.RECOMMENDED, SlotStatus.SCHEDULED, SlotStatus.CHANGED]).count(), 3)
        self.assertTrue(all(slot.status == SlotStatus.RECOMMENDED for slot in untouched_slots))


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

        date_response = self.client.get(f"/api/v1/plans/recovery-slots/history/?date={today}")
        self.assertEqual(date_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(date_response.data["data"]), 3)

        history_statuses = {item["id"]: item["history_status"] for item in date_response.data["data"]}
        self.assertEqual(history_statuses[str(missed_slot.id)], "MISSED")
        self.assertEqual(history_statuses[str(completed_slot.id)], "COMPLETED")
        self.assertEqual(history_statuses[str(upcoming_slot.id)], "UPCOMING")

        missed_item = next(item for item in date_response.data["data"] if item["id"] == str(missed_slot.id))
        self.assertEqual(missed_item["history_status_label"], "미완료")
        self.assertIn("목이 뻐근해요", missed_item["input_summary"])
        self.assertIn("과제", missed_item["input_summary"])
        self.assertIn("45분 예정", missed_item["input_summary"])
        self.assertEqual(missed_item["recommended_routines"][0]["activity"]["code"], "history_neck_shift")
        self.assertEqual(missed_item["recommended_routines"][0]["reason"], "목 긴장을 낮추기 위한 루틴입니다.")
        self.assertEqual(missed_item["remark"], "연속 사용 전에 짧은 휴식이 필요합니다.")
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

    @patch("plans.ai_planner.create_structured_response")
    def test_ai_generate_creates_plan_slots_routines_and_logs(self, mock_create_structured_response):
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

        shift = ActivityType.objects.create(
            code="shift_neck",
            stage_type=StageType.BRAIN_SHIFT,
            target_state=self.state,
            name="목 이완",
            default_duration_sec=90,
        )
        other_state, _ = StateOption.objects.get_or_create(
            code="EYE_TIRED",
            defaults={"label": "눈이 피곤해요"},
        )
        other_shift = ActivityType.objects.create(
            code="shift_eye",
            stage_type=StageType.BRAIN_SHIFT,
            target_state=other_state,
            name="눈 피로 완화",
            default_duration_sec=60,
        )
        first_time = (fixed_now + timedelta(minutes=30)).replace(microsecond=0)
        second_time = (fixed_now + timedelta(minutes=90)).replace(microsecond=0)
        mock_create_structured_response.return_value = (
            {
                "summary": "현재 상태와 PC 사용 패턴을 기준으로 두 번의 회복 세션을 추천합니다.",
                "slots": [
                    {
                        "recommended_at": first_time.isoformat(),
                        "interval_minutes": 30,
                        "reason": "첫 집중 구간 전에 긴장을 낮춥니다.",
                        "shift_recommendation": {
                            "activity_code": shift.code,
                            "difficulty_level": 3,
                            "planned_duration_sec": 90,
                            "reason": "목 뻐근함을 줄입니다.",
                        },
                    },
                    {
                        "recommended_at": second_time.isoformat(),
                        "interval_minutes": 60,
                        "reason": "연속 PC 사용 뒤 짧게 회복합니다.",
                        "shift_recommendation": {
                            "activity_code": other_shift.code,
                            "difficulty_level": 5,
                            "planned_duration_sec": 120,
                            "reason": "다른 상태의 활동을 잘못 골랐습니다.",
                        },
                    },
                ],
                "insights": [
                    {
                        "insight_type": "TODAY_ANALYSIS",
                        "body": "오늘은 PC 사용 패턴이 있는 날입니다.",
                        "data_sources": ["pc_usage_patterns"],
                    }
                ],
            },
            {"id": "resp_mock"},
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
        self.assertTrue(response.data["success"])
        self.assertIsNotNone(response.data["data"]["ai_plan_run"])
        self.assertEqual(len(response.data["data"]["slots"]), 2)
        self.assertEqual(response.data["data"]["slots"][0]["interval_minutes"], 45)
        for slot in response.data["data"]["slots"]:
            self.assertEqual(
                [routine["stage_type"] for routine in slot["routine_instances"]],
                [StageType.BRAIN_WAKE, StageType.BRAIN_SHIFT, StageType.BRAIN_RESET],
            )
            self.assertEqual(len(slot["routine_instances"]), 3)

        first_slot_routines = response.data["data"]["slots"][0]["routine_instances"]
        second_slot_routines = response.data["data"]["slots"][1]["routine_instances"]
        self.assertNotEqual(first_slot_routines[0]["activity"]["code"], second_slot_routines[0]["activity"]["code"])
        self.assertEqual(first_slot_routines[1]["activity"]["code"], shift.code)
        self.assertEqual(second_slot_routines[1]["activity"]["code"], shift.code)
        self.assertEqual(first_slot_routines[2]["stage_type"], StageType.BRAIN_RESET)
        self.assertEqual(second_slot_routines[2]["stage_type"], StageType.BRAIN_RESET)
        self.assertEqual(AIPlanRun.objects.count(), 1)
        self.assertEqual(AIInsight.objects.count(), 6)
        self.assertEqual(RoutineInstance.objects.count(), 6)

        input_messages = mock_create_structured_response.call_args.kwargs["input_messages"]
        input_snapshot = json.loads(input_messages[1]["content"][0]["text"])
        self.assertEqual(
            [activity["code"] for activity in input_snapshot["shift_activity_catalog"]],
            [shift.code],
        )
        self.assertEqual(input_snapshot["time_policy"]["interval_minutes"], 45)

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
