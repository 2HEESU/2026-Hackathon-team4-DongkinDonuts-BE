from django.db import models

from common.models import BaseModel


class FocusTimeOption(models.TextChoices):
    THIRTY_MINUTES = "THIRTY_MINUTES", "30분"
    ONE_HOUR = "ONE_HOUR", "1시간"
    TWO_HOURS = "TWO_HOURS", "2시간"
    CUSTOM = "CUSTOM", "직접 설정"
    SKIPPED = "SKIPPED", "건너뛰기"


# 온보딩에서 입력하는 '오늘의 상황' 1회분
class DailyContext(BaseModel):
    """ERD: daily_contexts. 온보딩 '오늘의 상황 입력' 1회분."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="daily_contexts")
    service_date = models.DateField(db_index=True)
    expected_focus_minutes = models.PositiveIntegerField(null=True, blank=True)
    focus_time_option = models.CharField(max_length=20, choices=FocusTimeOption.choices)
    skipped = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]
        indexes = [models.Index(fields=["user", "service_date"])]

    def __str__(self):
        return f"DailyContext({self.user_id}, {self.service_date})"


# DailyContext ↔ ActivityTag M2M 조인 테이블
class DailyContextActivityTag(models.Model):
    """ERD: daily_context_activity_tags (M2M 조인 테이블)."""

    daily_context = models.ForeignKey(DailyContext, on_delete=models.CASCADE, related_name="activity_tag_links")
    activity_tag = models.ForeignKey("common.ActivityTag", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["daily_context", "activity_tag"], name="unique_daily_context_activity_tag"
            )
        ]


# DailyContext ↔ StateOption M2M 조인 테이블(우선순위 포함)
class DailyContextState(models.Model):
    """ERD: daily_context_states. priority로 복수 선택 시 우선순위를 매긴다."""

    daily_context = models.ForeignKey(DailyContext, on_delete=models.CASCADE, related_name="state_links")
    state = models.ForeignKey("common.StateOption", on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["priority"]
        constraints = [
            models.UniqueConstraint(fields=["daily_context", "state"], name="unique_daily_context_state")
        ]
