import uuid

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from context.utils import today_for_user

from .services import DAY_ORDER


class PcUsagePatternApiTests(APITestCase):
    def setUp(self):
        self.device_code = uuid.uuid4()
        self.client.credentials(HTTP_X_DEVICE_CODE=str(self.device_code))
        # status 테스트에서 "오늘 요일"을 검증해야 해서, 인증이 자동 생성해줄 때까지
        # 기다리지 않고 User를 직접 만들어 timezone을 고정해둔다.
        self.user = User.objects.create(id=self.device_code, timezone="Asia/Seoul")
        self.today_day_of_week = DAY_ORDER[today_for_user(self.user).weekday()]
        self.other_day_of_week = next(day for day in DAY_ORDER if day != self.today_day_of_week)

    def test_bulk_replace_and_analysis(self):
        response = self.client.put(
            "/api/v1/digital-state/patterns/bulk/",
            [
                {"day_of_week": "MON", "hour": 9, "is_used": True},
                {"day_of_week": "MON", "hour": 10, "is_used": True},
                {"day_of_week": "TUE", "hour": 9, "is_used": True},
                {"day_of_week": "WED", "hour": 15, "is_used": False},
            ],
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 4)

        analysis_response = self.client.get("/api/v1/digital-state/patterns/analysis/")

        self.assertEqual(analysis_response.status_code, status.HTTP_200_OK)
        analysis = analysis_response.data["data"]
        self.assertEqual(analysis["weekly_pc_usage_hours"], 3)
        self.assertEqual(analysis["weekly_pc_usage_day_count"], 2)
        self.assertEqual(analysis["weekly_activity_rate"]["selected_cells"], 3)
        self.assertEqual(analysis["most_used_patterns"]["day_pattern"]["label"], "월")
        self.assertEqual(analysis["most_used_patterns"]["time_pattern"]["label"], "09:00 ~ 10:00")
        self.assertEqual(analysis["most_used_patterns"]["time_of_day_pattern"]["label"], "오전")

    def test_pattern_status_no_data(self):
        response = self.client.get("/api/v1/digital-state/patterns/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["data"], {"has_any_pattern": False, "has_pattern_for_today": False}
        )

    def test_pattern_status_other_day_only(self):
        # 오늘이 아닌 요일만 입력한 경우 — has_any_pattern은 True, has_pattern_for_today는 False.
        self.client.put(
            "/api/v1/digital-state/patterns/bulk/",
            [{"day_of_week": self.other_day_of_week, "hour": 9, "is_used": False}],
            format="json",
        )

        response = self.client.get("/api/v1/digital-state/patterns/status/")

        self.assertEqual(
            response.data["data"], {"has_any_pattern": True, "has_pattern_for_today": False}
        )

    def test_pattern_status_today_marked_unused_still_counts(self):
        # is_used=False로 명시한 것도 "데이터 없음"이 아니라 "입력함"으로 쳐야 한다
        # (모델 docstring의 구분 기준).
        self.client.put(
            "/api/v1/digital-state/patterns/bulk/",
            [{"day_of_week": self.today_day_of_week, "hour": 9, "is_used": False}],
            format="json",
        )

        response = self.client.get("/api/v1/digital-state/patterns/status/")

        self.assertEqual(
            response.data["data"], {"has_any_pattern": True, "has_pattern_for_today": True}
        )
