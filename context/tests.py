import uuid
from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from common.models import ActivityTag, StateOption

from .models import NextActivityPlan, UserContextSnapshot, UserContextSnapshotState
from .utils import today_for_user


class ContextApiTests(APITestCase):
    def setUp(self):
        self.device_code = uuid.uuid4()
        self.client.credentials(HTTP_X_DEVICE_CODE=str(self.device_code))
        self.state, _ = StateOption.objects.get_or_create(
            code="EYE_TIRED",
            defaults={"label": "눈이 피곤해요"},
        )
        self.activity_tag, _ = ActivityTag.objects.get_or_create(code="CODING", defaults={"name": "코딩"})

    def test_create_context_snapshot_without_skipped_flags(self):
        response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {
                "state_options": [self.state.code],
                "note": "오후 작업 전 상태",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        snapshot = UserContextSnapshot.objects.get(id=response.data["data"]["id"])
        self.assertEqual(list(snapshot.state_links.values_list("state_id", flat=True)), [self.state.code])
        self.assertNotIn("state_skipped", response.data["data"])
        self.assertNotIn("tags_skipped", response.data["data"])

    def test_create_next_activity_plan_separately_from_context_snapshot(self):
        snapshot_response = self.client.post(
            "/api/v1/context/context-snapshots/",
            {"state_options": [self.state.code]},
            format="json",
        )

        response = self.client.post(
            "/api/v1/context/next-activity-plans/",
            {
                "context_snapshot": snapshot_response.data["data"]["id"],
                "activity_tags": [self.activity_tag.code],
                "expected_activity_minutes": 90,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        activity_plan = NextActivityPlan.objects.get(id=response.data["data"]["id"])
        self.assertEqual(activity_plan.context_snapshot_id, UserContextSnapshot.objects.latest("created_at").id)
        self.assertEqual(activity_plan.expected_activity_minutes, 90)
        self.assertEqual(
            list(activity_plan.activity_tag_links.values_list("activity_tag_id", flat=True)),
            [self.activity_tag.code],
        )


class StateFrequencyApiTests(APITestCase):
    def setUp(self):
        self.device_code = uuid.uuid4()
        self.client.credentials(HTTP_X_DEVICE_CODE=str(self.device_code))
        self.user = User.objects.create(id=self.device_code, timezone="Asia/Seoul")
        self.eye_tired, _ = StateOption.objects.get_or_create(
            code="EYE_TIRED", defaults={"label": "눈이 피곤해요"}
        )
        self.sleepy, _ = StateOption.objects.get_or_create(code="SLEEPY", defaults={"label": "졸려요"})
        self.never_used, _ = StateOption.objects.get_or_create(
            code="NEVER_USED", defaults={"label": "테스트용"}
        )
        self.today = today_for_user(self.user)

    def _create_snapshot(self, state, service_date):
        snapshot = UserContextSnapshot.objects.create(user=self.user, service_date=service_date)
        UserContextSnapshotState.objects.create(context_snapshot=snapshot, state=state, priority=1)
        return snapshot

    def test_counts_and_zero_fill_for_unused_states(self):
        self._create_snapshot(self.eye_tired, self.today)
        self._create_snapshot(self.eye_tired, self.today - timedelta(days=1))
        self._create_snapshot(self.sleepy, self.today)

        response = self.client.get("/api/v1/context/state-frequency/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_code = {item["code"]: item["count"] for item in response.data["data"]}
        self.assertEqual(by_code[self.eye_tired.code], 2)
        self.assertEqual(by_code[self.sleepy.code], 1)
        self.assertEqual(by_code[self.never_used.code], 0)

    def test_sorted_descending_by_count(self):
        self._create_snapshot(self.eye_tired, self.today)
        self._create_snapshot(self.eye_tired, self.today - timedelta(days=1))
        self._create_snapshot(self.sleepy, self.today)

        response = self.client.get("/api/v1/context/state-frequency/")

        codes_in_order = [item["code"] for item in response.data["data"]]
        self.assertEqual(codes_in_order[0], self.eye_tired.code)

    def test_excludes_snapshots_outside_days_window(self):
        self._create_snapshot(self.eye_tired, self.today - timedelta(days=40))

        response = self.client.get("/api/v1/context/state-frequency/?days=30")

        by_code = {item["code"]: item["count"] for item in response.data["data"]}
        self.assertEqual(by_code[self.eye_tired.code], 0)

    def test_invalid_days_rejected(self):
        response = self.client.get("/api/v1/context/state-frequency/?days=0")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
