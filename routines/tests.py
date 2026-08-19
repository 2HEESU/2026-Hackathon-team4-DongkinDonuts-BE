from rest_framework import status
from rest_framework.test import APITestCase

from .models import ActivityType, StageType


class ActivityTypeListViewTest(APITestCase):
    def setUp(self):
        self.active_activity, _ = ActivityType.objects.update_or_create(
            code="WAKE_EYE_MOVE",
            defaults={
                "stage_type": StageType.BRAIN_WAKE,
                "name": "시선 움직이기",
                "purpose": "눈과 시선을 깨웁니다.",
                "required_landmarks": ["LEFT_EYE", "RIGHT_EYE"],
                "min_difficulty": 1,
                "max_difficulty": 3,
                "default_duration_sec": 60,
                "is_active": True,
            },
        )

    def test_active_activity_types_are_returned(self):
        response = self.client.get("/api/v1/routines/activity-types/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["message"])

        activities = response.data["data"]

        self.assertIn(
            self.active_activity.code,
            [activity["code"] for activity in activities],
        )
