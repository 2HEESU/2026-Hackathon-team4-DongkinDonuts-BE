from django.db import models
from django.db.models import Q

from common.constants import CameraPermissionStatus
from common.models import BaseModel


class SessionStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "진행중"
    COMPLETED = "COMPLETED", "완료"
    ABORTED = "ABORTED", "중도종료"
    # RESET은 별도 상태로 두지 않는다 — GET /sessions/active/가 IN_PROGRESS만 조회하는데
    # 초기화 시 상태를 RESET으로 바꾸면 새로고침/화면 복귀 시 조회가 안 되는 문제가 생김.
    # 초기화는 상태를 IN_PROGRESS로 유지한 채 reset_count만 증가시키고, 필요하면
    # SessionEvent에 RESET 이벤트를 별도로 남긴다.


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
        constraints = [
            # 같은 루틴에 대해 진행중 세션이 동시에 2개 생기는 걸 막는다(핵심 무결성 규칙).
            models.UniqueConstraint(
                fields=["routine_instance"],
                condition=Q(status=SessionStatus.IN_PROGRESS),
                name="unique_active_session_per_routine_instance",
            ),
            # 한 사용자가 시스템 전체에서 동시에 진행중 세션을 2개 이상 갖지 못하게 막는
            # 예외적 안전장치(정상 흐름에선 locked_until_previous_done 때문에 어차피 안 생김).
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status=SessionStatus.IN_PROGRESS),
                name="unique_active_session_per_user",
            ),
        ]

    def __str__(self):
        return f"Session({self.routine_instance_id}, {self.status})"


# (참고) SessionMetricSample(시점별 측정값 타임시리즈)은 삭제함 — 실시간 자세 교정은
# 프론트 MediaPipe가 클라이언트에서 직접 처리하고(ActivityType.required_landmarks 참고),
# 그 세부 측정값을 서버에 저장해서 나중에 리포트 등으로 활용할 계획이 없음. 세션 종료 시
# 요약값(정확도 등)만 Session.accuracy/metrics에 담아서 보내면 됨.


# 세션 중 발생한 이벤트 로그(카메라 끊김 등)
class SessionEvent(BaseModel):
    """ERD: session_events. 세션 중 발생한 이벤트 로그(카메라 끊김 등)."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50)
    step_no = models.PositiveSmallIntegerField(null=True, blank=True)
    message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["session", "created_at"]


# 회복 슬롯(방문) 단위 사용자 피드백 — Wake/Shift/Reset 3개 세션이 아니라 슬롯당 1건
class SessionFeedback(BaseModel):
    """
    ERD: session_feedback. 원래 Session에 OneToOne으로 걸려 있었는데, 세션이 RoutineInstance당
    하나씩(방문당 3개) 생기는 구조라 피드백도 3번 물어보게 되는 문제가 있었음. IA 08번을 보면
    피드백은 Wake→Shift→Reset 전체 완료 후 한 번만 묻는 흐름이라, RecoverySlot(방문 단위)에
    걸리도록 수정함. 모델 이름은 과거 이름을 그대로 유지(sessions_app에 남겨둠 — 앱을 옮기는 건
    실익 대비 마이그레이션 비용이 커서 보류).
    """

    recovery_slot = models.OneToOneField(
        "plans.RecoverySlot", on_delete=models.CASCADE, related_name="feedback"
    )
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="session_feedbacks")
    recovery_feeling = models.CharField(max_length=20, choices=RecoveryFeeling.choices, null=True, blank=True)
    difficulty_feedback = models.CharField(
        max_length=20, choices=DifficultyFeedback.choices, null=True, blank=True
    )
    skipped = models.BooleanField(default=False)
