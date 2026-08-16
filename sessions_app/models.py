from django.db import models

from common.constants import CameraPermissionStatus
from common.models import BaseModel


class SessionStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "진행중"
    COMPLETED = "COMPLETED", "완료"
    ABORTED = "ABORTED", "중도종료"
    RESET = "RESET", "초기화됨"


class RecoveryFeeling(models.TextChoices):
    MUCH_BETTER = "MUCH_BETTER", "훨씬 나아졌어요"
    SLIGHTLY_BETTER = "SLIGHTLY_BETTER", "조금 나아졌어요"
    SAME = "SAME", "비슷해요"


class DifficultyFeedback(models.TextChoices):
    JUST_RIGHT = "JUST_RIGHT", "딱 좋았어요"
    TOO_EASY = "TOO_EASY", "너무 쉬웠어요"
    A_BIT_HARD = "A_BIT_HARD", "조금 힘들었어요"


# RoutineInstance의 실제 실행 기록
class Session(BaseModel):
    """ERD: sessions. routine_instance 하나에 대한 실제 실행 기록."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="sessions")
    recovery_slot = models.ForeignKey(
        "plans.RecoverySlot", on_delete=models.CASCADE, related_name="sessions"
    )
    routine_instance = models.ForeignKey(
        "routines.RoutineInstance", on_delete=models.CASCADE, related_name="sessions"
    )
    activity = models.ForeignKey(
        "routines.ActivityType", on_delete=models.PROTECT, related_name="sessions"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_sec = models.PositiveIntegerField(null=True, blank=True)
    accuracy = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0~100")
    streak_count = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.IN_PROGRESS)
    camera_permission_status = models.CharField(
        max_length=20, choices=CameraPermissionStatus.choices, default=CameraPermissionStatus.UNKNOWN
    )
    reset_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Session({self.routine_instance_id}, {self.status})"


# 세션 진행 중 시점별 측정값(타임시리즈)
class SessionMetricSample(BaseModel):
    """ERD: session_metric_samples. 세션 진행 중 여러 시점의 측정값(타임시리즈)."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="metric_samples")
    step_no = models.PositiveSmallIntegerField()
    metric_type = models.CharField(max_length=50)
    accuracy_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reaction_ms = models.PositiveIntegerField(null=True, blank=True)
    screen_distance_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    raw_payload_json = models.JSONField(null=True, blank=True)
    measured_at = models.DateTimeField()

    class Meta:
        ordering = ["session", "step_no"]


# 세션 중 발생한 이벤트 로그(카메라 끊김 등)
class SessionEvent(BaseModel):
    """ERD: session_events. 세션 중 발생한 이벤트 로그(카메라 끊김 등)."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50)
    step_no = models.PositiveSmallIntegerField(null=True, blank=True)
    message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["session", "created_at"]


# 세션 종료 후 사용자 피드백(세션 1건당 1건)
class SessionFeedback(BaseModel):
    """ERD: session_feedback. 세션 하나당 1건(OneToOne)이 자연스러워서 그렇게 제약함."""

    session = models.OneToOneField(Session, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="session_feedbacks")
    recovery_feeling = models.CharField(max_length=20, choices=RecoveryFeeling.choices, null=True, blank=True)
    difficulty_feedback = models.CharField(
        max_length=20, choices=DifficultyFeedback.choices, null=True, blank=True
    )
    skipped = models.BooleanField(default=False)
