from django.test import TestCase

# Create your tests here.
import json

from rest_framework import status
from rest_framework.test import APITestCase

from .models import ActivityType, StageType


class ActivityTypeListViewTest(APITestCase):
    def setUp(self):
        self.active_activity = ActivityType.objects.create(
            code="WAKE_EYE_MOVE",
            stage_type=StageType.BRAIN_WAKE,
            name="시선 움직이기",
            purpose="눈과 시선을 깨웁니다.",
            required_landmarks=["LEFT_EYE", "RIGHT_EYE"],
            min_difficulty=1,
            max_difficulty=3,
            default_duration_sec=60,
            is_active=True,
        )

    def test_active_activity_types_are_returned(self):
        response = self.client.get("/api/v1/routines/activity-types/")

        print(
            json.dumps(
                response.data,
                ensure_ascii=False,
                indent=2,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["message"])

        activities = response.data["data"]

        self.assertEqual(len(activities), 1)
        self.assertEqual(
            activities[0]["code"],
            self.active_activity.code,
        )