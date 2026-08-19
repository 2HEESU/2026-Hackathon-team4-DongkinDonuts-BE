from django.test import TestCase

# Create your tests here.
from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.constants import CameraPermissionStatus
from context.models import DailyContext, FocusTimeOption
from plans.models import (
    Notification,
    NotificationStatus,
    RecoveryPlan,
    RecoverySlot,
    SlotStatus,
)
from routines.models import (
    ActivityType,
    RoutineInstance,
    RoutineInstanceStatus,
    StageType,
)

from .models import Session, SessionStatus


class SessionApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create()
        self.client.credentials(
            HTTP_X_DEVICE_CODE=str(self.user.id),
        )

        daily_context = DailyContext.objects.create(
            user=self.user,
            service_date=date.today(),
            focus_time_option=FocusTimeOption.SKIPPED,
            state_skipped=True,
            tags_skipped=True,
        )

        recovery_plan = RecoveryPlan.objects.create(
            user=self.user,
            daily_context=daily_context,
            plan_date=date.today(),
        )

        self.recovery_slot = RecoverySlot.objects.create(
            recovery_plan=recovery_plan,
            sequence_no=1,
            recommended_at=timezone.now() + timedelta(minutes=47),
            scheduled_at=timezone.now() + timedelta(minutes=47),
            status=SlotStatus.SCHEDULED,
        )

        self.notification = Notification.objects.create(
            recovery_slot=self.recovery_slot,
            message="잠깐 리셋할 시간이에요.",
            scheduled_at=self.recovery_slot.scheduled_at,
            status=NotificationStatus.PENDING,
        )

        self.activity = ActivityType.objects.create(
            code="WAKE_TEST",
            stage_type=StageType.BRAIN_WAKE,
            name="테스트 활동",
            purpose="세션 시작 테스트",
            required_landmarks=[],
            min_difficulty=1,
            max_difficulty=5,
            default_duration_sec=60,
            is_active=True,
        )

        self.routine_instance = RoutineInstance.objects.create(
            recovery_slot=self.recovery_slot,
            activity=self.activity,
            sequence_no=1,
            difficulty_level=1,
            planned_duration_sec=60,
            status=RoutineInstanceStatus.AVAILABLE,
            locked_until_previous_done=False,
        )

    def test_session_can_start_before_scheduled_time(self):
        response = self.client.post(
            "/api/v1/sessions/",
            {
                "routine_instance_id": str(
                    self.routine_instance.id,
                ),
                "camera_permission_status": (
                    CameraPermissionStatus.GRANTED
                ),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.recovery_slot.refresh_from_db()
        self.notification.refresh_from_db()
        self.routine_instance.refresh_from_db()

        self.assertEqual(
            self.recovery_slot.status,
            SlotStatus.STARTED,
        )
        self.assertEqual(
            self.notification.status,
            NotificationStatus.CANCELED,
        )
        self.assertEqual(
            self.routine_instance.status,
            RoutineInstanceStatus.IN_PROGRESS,
        )

        self.assertTrue(
            Session.objects.filter(
                user=self.user,
                routine_instance=self.routine_instance,
                status=SessionStatus.IN_PROGRESS,
            ).exists()
        )

    def test_active_session_returns_null_when_not_found(self):
        response = self.client.get(
            "/api/v1/sessions/active/",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["data"])

    def test_duplicate_active_session_is_rejected(self):
        self.client.post(
            "/api/v1/sessions/",
            {
                "routine_instance_id": str(
                    self.routine_instance.id,
                ),
                "camera_permission_status": (
                    CameraPermissionStatus.GRANTED
                ),
            },
            format="json",
        )

        response = self.client.post(
            "/api/v1/sessions/",
            {
                "routine_instance_id": str(
                    self.routine_instance.id,
                ),
                "camera_permission_status": (
                    CameraPermissionStatus.GRANTED
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409)

    def test_session_reset_starts_from_first_step(self):
        session = Session.objects.create(
            user=self.user,
            recovery_slot=self.recovery_slot,
            routine_instance=self.routine_instance,
            activity=self.activity,
            started_at=timezone.now() - timedelta(minutes=2),
            duration_sec=120,
            accuracy=80,
            streak_count=5,
            metrics={"step": 3},
            status=SessionStatus.IN_PROGRESS,
            camera_permission_status=(
                CameraPermissionStatus.GRANTED
            ),
        )

        self.routine_instance.status = (
            RoutineInstanceStatus.IN_PROGRESS
        )
        self.routine_instance.save()

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/reset/",
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        session.refresh_from_db()

        self.assertEqual(session.reset_count, 1)
        self.assertEqual(
            session.status,
            SessionStatus.IN_PROGRESS,
        )
        self.assertIsNone(session.duration_sec)
        self.assertIsNone(session.accuracy)
        self.assertEqual(session.streak_count, 0)
        self.assertIsNone(session.metrics)
        self.assertTrue(
            session.events.filter(event_type="RESET").exists()
        )