import uuid

from rest_framework import status
from rest_framework.test import APITestCase


class PcUsagePatternApiTests(APITestCase):
    def setUp(self):
        self.client.credentials(HTTP_X_DEVICE_CODE=str(uuid.uuid4()))

    def test_bulk_replace_and_analysis(self):
        response = self.client.put(
            "/api/v1/digital-state/pc-usage-patterns/",
            {
                "patterns": [
                    {"day_of_week": "MON", "hour": 9, "is_used": True},
                    {"day_of_week": "MON", "hour": 10, "is_used": True},
                    {"day_of_week": "TUE", "hour": 9, "is_used": True},
                    {"day_of_week": "WED", "hour": 15, "is_used": False},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 4)

        analysis_response = self.client.get("/api/v1/digital-state/pc-usage-patterns/analysis/")

        self.assertEqual(analysis_response.status_code, status.HTTP_200_OK)
        analysis = analysis_response.data["data"]
        self.assertEqual(analysis["weekly_pc_usage_hours"], 3)
        self.assertEqual(analysis["weekly_pc_usage_day_count"], 2)
        self.assertEqual(analysis["weekly_activity_rate"]["selected_cells"], 3)
        self.assertEqual(analysis["most_used_patterns"]["day_pattern"]["label"], "월")
        self.assertEqual(analysis["most_used_patterns"]["time_pattern"]["label"], "09:00 ~ 10:00")
        self.assertEqual(analysis["most_used_patterns"]["time_of_day_pattern"]["label"], "오전")
