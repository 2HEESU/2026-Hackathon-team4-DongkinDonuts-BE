from django.db import models

from common.models import BaseModel


class StageType(models.TextChoices):
    BRAIN_WAKE = "BRAIN_WAKE", "Brain Wake"
    BRAIN_SHIFT = "BRAIN_SHIFT", "Brain Shift"
    BRAIN_RESET = "BRAIN_RESET", "Brain Reset"


class RoutineInstanceStatus(models.TextChoices):
    LOCKED = "LOCKED", "잠김"
    AVAILABLE = "AVAILABLE", "진행 가능"
    IN_PROGRESS = "IN_PROGRESS", "진행중"
    COMPLETED = "COMPLETED", "완료"
    ABORTED = "ABORTED", "중도종료"


# 사전 정의된 활동 카탈로그(운영 데이터)
class ActivityType(models.Model):
    """
    ERD: activity_types. 사전 정의된 활동 카탈로그(운영 데이터라 code가 자연키/PK).
    required_landmarks: 프론트 MediaPipe가 이 활동에서 추적해야 할 landmark 목록.
    """

    code = models.CharField(max_length=50, primary_key=True)
    stage_type = models.CharField(max_length=20, choices=StageType.choices)
    target_state = models.ForeignKey(
        "common.StateOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_types",
        help_text="Brain Shift에서만 사용. Wake/Reset은 null",
    )
    name = models.CharField(max_length=100)
    purpose = models.TextField(blank=True)
    required_landmarks = models.JSONField(default=list, blank=True)
    min_difficulty = models.PositiveSmallIntegerField(default=1)
    max_difficulty = models.PositiveSmallIntegerField(default=5)
    default_duration_sec = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.name})"


# RecoverySlot 하나에 속한 Wake/Shift/Reset 활동 1건
class RoutineInstance(BaseModel):
    """
    ERD: routine_instances. recovery_slot 하나당 Wake/Shift/Reset 3개 row가 생긴다.
    ai_reason 컬럼은 제거됨 — plans.AIInsight(routine_instance_id로 연결)로 일원화.
    """

    recovery_slot = models.ForeignKey(
        "plans.RecoverySlot", on_delete=models.CASCADE, related_name="routine_instances"
    )
    activity = models.ForeignKey(
        ActivityType, on_delete=models.PROTECT, related_name="routine_instances"
    )
    sequence_no = models.PositiveSmallIntegerField(help_text="1=Wake, 2=Shift, 3=Reset")
    stage_type = models.CharField(max_length=20, choices=StageType.choices)
    difficulty_level = models.PositiveSmallIntegerField()
    planned_duration_sec = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=RoutineInstanceStatus.choices, default=RoutineInstanceStatus.LOCKED
    )
    locked_until_previous_done = models.BooleanField(default=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["recovery_slot", "sequence_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["recovery_slot", "sequence_no"], name="unique_routine_instance_sequence"
            )
        ]

    def __str__(self):
        return f"RoutineInstance(slot={self.recovery_slot_id}, #{self.sequence_no}, {self.stage_type})"
