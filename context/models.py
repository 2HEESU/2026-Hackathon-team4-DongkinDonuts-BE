from django.db import models

from common.models import BaseModel


class UserContextSnapshot(BaseModel):
    """
    사용자가 특정 시점에 입력한 '지금 내 상태' 스냅샷.

    하루 전체를 대표하는 값이 아니라 서비스 진입, 알림 재진입 등 사용자가 상태를 다시
    제출하는 순간마다 새로 쌓이는 불변 기록이다. 이후 활동 종류/시간은 생명주기가 달라서
    NextActivityPlan으로 분리한다.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="context_snapshots")
    service_date = models.DateField(db_index=True)
    state_options = models.ManyToManyField(
        "common.StateOption",
        through="UserContextSnapshotState",
        related_name="context_snapshots",
        blank=True,
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]

    def __str__(self):
        return f"UserContextSnapshot({self.user_id}, {self.service_date})"


class UserContextSnapshotState(models.Model):
    """UserContextSnapshot ↔ StateOption M2M 조인 테이블. priority로 복수 선택 순서를 보존한다."""

    context_snapshot = models.ForeignKey(
        UserContextSnapshot, on_delete=models.CASCADE, related_name="state_links"
    )
    state = models.ForeignKey("common.StateOption", on_delete=models.PROTECT)
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["priority"]
        constraints = [
            models.UniqueConstraint(
                fields=["context_snapshot", "state"], name="unique_context_snapshot_state"
            )
        ]


class NextActivityPlan(BaseModel):
    """
    사용자가 입력한 '앞으로의 활동 종류와 활동 시간' 기록.

    내 계획 다시 설정은 상태 스냅샷을 새로 만들지 않고 이 모델만 새로 쌓는다. 시간을
    건너뛴 경우에는 expected_activity_minutes를 null로 둔다.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="next_activity_plans")
    context_snapshot = models.ForeignKey(
        UserContextSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_activity_plans",
    )
    service_date = models.DateField(db_index=True)
    activity_tags = models.ManyToManyField(
        "common.ActivityTag",
        through="NextActivityPlanActivityTag",
        related_name="next_activity_plans",
        blank=True,
    )
    expected_activity_minutes = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]

    def __str__(self):
        return f"NextActivityPlan({self.user_id}, {self.service_date}, {self.expected_activity_minutes})"


class NextActivityPlanActivityTag(models.Model):
    """NextActivityPlan ↔ ActivityTag M2M 조인 테이블."""

    next_activity_plan = models.ForeignKey(
        NextActivityPlan, on_delete=models.CASCADE, related_name="activity_tag_links"
    )
    activity_tag = models.ForeignKey("common.ActivityTag", on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["next_activity_plan", "activity_tag"], name="unique_next_activity_plan_tag"
            )
        ]
