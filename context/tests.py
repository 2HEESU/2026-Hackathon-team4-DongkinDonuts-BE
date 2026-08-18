import uuid

from rest_framework import status
from rest_framework.test import APITestCase

from common.models import ActivityTag, StateOption

from .models import NextActivityPlan, UserContextSnapshot


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
