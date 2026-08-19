from datetime import date, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.constants import CameraPermissionStatus
from context.models import DailyContext, FocusTimeOption
from plans.models import (
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


class SessionAbortCompleteApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create()

        self.client.credentials(
            HTTP_X_DEVICE_CODE=str(self.user.id),
        )

        self.daily_context = DailyContext.objects.create(
            user=self.user,
            service_date=date.today(),
            focus_time_option=FocusTimeOption.SKIPPED,
            tags_skipped=True,
        )

        self.recovery_plan = RecoveryPlan.objects.create(
            user=self.user,
            daily_context=self.daily_context,
            plan_date=date.today(),
        )

        self.recovery_slot = RecoverySlot.objects.create(
            recovery_plan=self.recovery_plan,
            sequence_no=1,
            recommended_at=timezone.now(),
            scheduled_at=timezone.now(),
            status=SlotStatus.STARTED,
        )

        self.wake_activity = ActivityType.objects.create(
            code="WAKE_TEST",
            stage_type=StageType.BRAIN_WAKE,
            name="Brain Wake 테스트",
            purpose="Brain Wake 테스트 활동",
            required_landmarks=[],
            min_difficulty=1,
            max_difficulty=5,
            default_duration_sec=60,
            is_active=True,
        )

        self.shift_activity = ActivityType.objects.create(
            code="SHIFT_TEST",
            stage_type=StageType.BRAIN_SHIFT,
            name="Brain Shift 테스트",
            purpose="Brain Shift 테스트 활동",
            required_landmarks=[],
            min_difficulty=1,
            max_difficulty=5,
            default_duration_sec=60,
            is_active=True,
        )

        self.reset_activity = ActivityType.objects.create(
            code="RESET_TEST",
            stage_type=StageType.BRAIN_RESET,
            name="Brain Reset 테스트",
            purpose="Brain Reset 테스트 활동",
            required_landmarks=[],
            min_difficulty=1,
            max_difficulty=5,
            default_duration_sec=60,
            is_active=True,
        )

        self.wake_routine = RoutineInstance.objects.create(
            recovery_slot=self.recovery_slot,
            activity=self.wake_activity,
            sequence_no=1,
            difficulty_level=1,
            planned_duration_sec=60,
            status=RoutineInstanceStatus.COMPLETED,
            locked_until_previous_done=False,
            completed_at=timezone.now() - timedelta(minutes=3),
        )

        self.shift_routine = RoutineInstance.objects.create(
            recovery_slot=self.recovery_slot,
            activity=self.shift_activity,
            sequence_no=2,
            difficulty_level=1,
            planned_duration_sec=60,
            status=RoutineInstanceStatus.IN_PROGRESS,
            locked_until_previous_done=False,
        )

        self.reset_routine = RoutineInstance.objects.create(
            recovery_slot=self.recovery_slot,
            activity=self.reset_activity,
            sequence_no=3,
            difficulty_level=1,
            planned_duration_sec=60,
            status=RoutineInstanceStatus.LOCKED,
            locked_until_previous_done=True,
        )

    def _create_in_progress_session(
        self,
        routine_instance=None,
        seconds_ago=65,
    ):
        routine_instance = (
            routine_instance or self.shift_routine
        )

        routine_instance.status = (
            RoutineInstanceStatus.IN_PROGRESS
        )
        routine_instance.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return Session.objects.create(
            user=self.user,
            recovery_slot=self.recovery_slot,
            routine_instance=routine_instance,
            activity=routine_instance.activity,
            started_at=(
                timezone.now()
                - timedelta(seconds=seconds_ago)
            ),
            status=SessionStatus.IN_PROGRESS,
            camera_permission_status=(
                CameraPermissionStatus.GRANTED
            ),
        )

    def test_abort_changes_only_current_session_and_routine(self):
        session = self._create_in_progress_session()

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/abort/",
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        session.refresh_from_db()
        self.wake_routine.refresh_from_db()
        self.shift_routine.refresh_from_db()
        self.reset_routine.refresh_from_db()
        self.recovery_slot.refresh_from_db()

        self.assertEqual(
            session.status,
            SessionStatus.ABORTED,
        )
        self.assertIsNotNone(session.ended_at)
        self.assertGreaterEqual(session.duration_sec, 60)

        self.assertEqual(
            self.wake_routine.status,
            RoutineInstanceStatus.COMPLETED,
        )

        self.assertEqual(
            self.shift_routine.status,
            RoutineInstanceStatus.AVAILABLE,
        )
        self.assertIsNone(
            self.shift_routine.completed_at,
        )

        self.assertEqual(
            self.reset_routine.status,
            RoutineInstanceStatus.LOCKED,
        )
        self.assertTrue(
            self.reset_routine.locked_until_previous_done,
        )

        self.assertEqual(
            self.recovery_slot.status,
            SlotStatus.STARTED,
        )

        self.assertEqual(
            response.data["data"]["status"],
            SessionStatus.ABORTED,
        )

    def test_aborted_routine_can_be_started_again(self):
        session = self._create_in_progress_session()

        abort_response = self.client.patch(
            f"/api/v1/sessions/{session.id}/abort/",
            {},
            format="json",
        )

        self.assertEqual(
            abort_response.status_code,
            status.HTTP_200_OK,
        )

        restart_response = self.client.post(
            "/api/v1/sessions/",
            {
                "routine_instance_id": str(
                    self.shift_routine.id
                ),
                "camera_permission_status": (
                    CameraPermissionStatus.GRANTED
                ),
            },
            format="json",
        )

        self.assertEqual(
            restart_response.status_code,
            status.HTTP_201_CREATED,
        )

        self.shift_routine.refresh_from_db()

        self.assertEqual(
            self.shift_routine.status,
            RoutineInstanceStatus.IN_PROGRESS,
        )

        self.assertEqual(
            Session.objects.filter(
                routine_instance=self.shift_routine,
                status=SessionStatus.IN_PROGRESS,
            ).count(),
            1,
        )

    def test_completed_session_cannot_be_aborted(self):
        session = self._create_in_progress_session()

        session.status = SessionStatus.COMPLETED
        session.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/abort/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 409)

    def test_complete_saves_results_and_unlocks_next_routine(self):
        session = self._create_in_progress_session()

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/complete/",
            {
                "accuracy": 87,
                "metrics": {
                    "reaction_average_ms": 420,
                },
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        session.refresh_from_db()
        self.wake_routine.refresh_from_db()
        self.shift_routine.refresh_from_db()
        self.reset_routine.refresh_from_db()
        self.recovery_slot.refresh_from_db()

        self.assertEqual(
            session.status,
            SessionStatus.COMPLETED,
        )
        self.assertEqual(session.accuracy, 87)
        self.assertEqual(
            session.metrics,
            {
                "reaction_average_ms": 420,
            },
        )
        self.assertIsNotNone(session.ended_at)
        self.assertGreaterEqual(session.duration_sec, 60)

        self.assertEqual(
            self.wake_routine.status,
            RoutineInstanceStatus.COMPLETED,
        )

        self.assertEqual(
            self.shift_routine.status,
            RoutineInstanceStatus.COMPLETED,
        )
        self.assertIsNotNone(
            self.shift_routine.completed_at,
        )

        self.assertEqual(
            self.reset_routine.status,
            RoutineInstanceStatus.AVAILABLE,
        )
        self.assertFalse(
            self.reset_routine.locked_until_previous_done,
        )

        self.assertEqual(
            self.recovery_slot.status,
            SlotStatus.STARTED,
        )

        response_data = response.data["data"]

        self.assertEqual(
            response_data["status"],
            SessionStatus.COMPLETED,
        )
        self.assertNotIn(
            "streak_count",
            response_data,
        )
        self.assertNotIn(
            "next_routine_instance",
            response_data,
        )
        self.assertNotIn(
            "next_routine_instance_id",
            response_data,
        )

    def test_last_routine_complete_completes_recovery_slot(self):
        self.shift_routine.status = (
            RoutineInstanceStatus.COMPLETED
        )
        self.shift_routine.completed_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.shift_routine.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        self.reset_routine.status = (
            RoutineInstanceStatus.IN_PROGRESS
        )
        self.reset_routine.locked_until_previous_done = False
        self.reset_routine.save(
            update_fields=[
                "status",
                "locked_until_previous_done",
                "updated_at",
            ]
        )

        session = self._create_in_progress_session(
            routine_instance=self.reset_routine,
        )

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/complete/",
            {
                "accuracy": 92,
                "metrics": {
                    "reaction_average_ms": 380,
                },
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        session.refresh_from_db()
        self.reset_routine.refresh_from_db()
        self.recovery_slot.refresh_from_db()

        self.assertEqual(
            session.status,
            SessionStatus.COMPLETED,
        )
        self.assertEqual(
            self.reset_routine.status,
            RoutineInstanceStatus.COMPLETED,
        )
        self.assertIsNotNone(
            self.reset_routine.completed_at,
        )
        self.assertEqual(
            self.recovery_slot.status,
            SlotStatus.COMPLETED,
        )

    def test_complete_allows_metrics_to_be_omitted(self):
        session = self._create_in_progress_session()

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/complete/",
            {
                "accuracy": 80,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        session.refresh_from_db()

        self.assertEqual(
            session.status,
            SessionStatus.COMPLETED,
        )
        self.assertEqual(session.accuracy, 80)
        self.assertIsNone(session.metrics)

    def test_complete_rejects_invalid_accuracy(self):
        session = self._create_in_progress_session()

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/complete/",
            {
                "accuracy": 101,
                "metrics": None,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        session.refresh_from_db()
        self.shift_routine.refresh_from_db()
        self.reset_routine.refresh_from_db()

        self.assertEqual(
            session.status,
            SessionStatus.IN_PROGRESS,
        )
        self.assertEqual(
            self.shift_routine.status,
            RoutineInstanceStatus.IN_PROGRESS,
        )
        self.assertEqual(
            self.reset_routine.status,
            RoutineInstanceStatus.LOCKED,
        )

    def test_aborted_session_cannot_be_completed(self):
        session = self._create_in_progress_session()

        session.status = SessionStatus.ABORTED
        session.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        response = self.client.patch(
            f"/api/v1/sessions/{session.id}/complete/",
            {
                "accuracy": 85,
                "metrics": None,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409)

    def test_other_user_cannot_abort_or_complete_session(self):
        session = self._create_in_progress_session()

        other_user = User.objects.create()

        self.client.credentials(
            HTTP_X_DEVICE_CODE=str(other_user.id),
        )

        abort_response = self.client.patch(
            f"/api/v1/sessions/{session.id}/abort/",
            {},
            format="json",
        )

        complete_response = self.client.patch(
            f"/api/v1/sessions/{session.id}/complete/",
            {
                "accuracy": 90,
                "metrics": None,
            },
            format="json",
        )

        self.assertEqual(
            abort_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            complete_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        session.refresh_from_db()

        self.assertEqual(
            session.status,
            SessionStatus.IN_PROGRESS,
        )