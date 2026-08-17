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
    # service_date는 클라이언트가 보내지 않는다 — User.timezone 기준으로 서버가 "오늘"을 계산해서
    # 채운다. /today/ 조회 및 아래 unique 제약과 항상 일치시키기 위함.
    service_date = models.DateField(db_index=True)
    expected_focus_minutes = models.PositiveIntegerField(null=True, blank=True)
    focus_time_option = models.CharField(max_length=20, choices=FocusTimeOption.choices)
    # 항목별로 건너뛸 수 있어서 전체용 skipped 하나로는 표현 불가.
    # 집중시간 건너뛰기는 focus_time_option=SKIPPED로 이미 표현됨.
    state_skipped = models.BooleanField(default=False, help_text="현재 상태 선택을 건너뛰었는지")
    tags_skipped = models.BooleanField(default=False, help_text="활동 태그 선택을 건너뛰었는지")
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "service_date"], name="unique_user_service_date")
        ]

    def __str__(self):
        return f"DailyContext({self.user_id}, {self.service_date})"


# DailyContext ↔ ActivityTag M2M 조인 테이블
class DailyContextActivityTag(models.Model):
    """ERD: daily_context_activity_tags (M2M 조인 테이블)."""

    daily_context = models.ForeignKey(DailyContext, on_delete=models.CASCADE, related_name="activity_tag_links")
    # PROTECT: 태그가 비활성화(is_active=False)될 수는 있어도, 사용자가 과거에 선택한 기록이
    # 남아있는 한 하드 삭제는 막는다.
    activity_tag = models.ForeignKey("common.ActivityTag", on_delete=models.PROTECT)

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
    state = models.ForeignKey("common.StateOption", on_delete=models.PROTECT)
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["priority"]
        constraints = [
            models.UniqueConstraint(fields=["daily_context", "state"], name="unique_daily_context_state")
        ]
