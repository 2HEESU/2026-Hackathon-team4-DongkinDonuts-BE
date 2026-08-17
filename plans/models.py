from django.db import models
from django.db.models import Q

from common.models import BaseModel


class SlotStatus(models.TextChoices):
    RECOMMENDED = "RECOMMENDED", "추천됨"
    SCHEDULED = "SCHEDULED", "예약됨"
    CHANGED = "CHANGED", "변경됨"
    CANCELED = "CANCELED", "취소됨"
    STARTED = "STARTED", "시작됨"
    COMPLETED = "COMPLETED", "완료"
    MISSED = "MISSED", "놓침"


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", "대기중"
    SENT = "SENT", "발송됨"
    CLICKED = "CLICKED", "클릭됨"
    FAILED = "FAILED", "실패"
    CANCELED = "CANCELED", "취소됨"


class InsightType(models.TextChoices):
    TODAY_ANALYSIS = "TODAY_ANALYSIS", "오늘의 분석"
    RECOMMENDATION_REASON = "RECOMMENDATION_REASON", "추천 이유"
    ROUTINE_REASON = "ROUTINE_REASON", "루틴 이유"
    # ERD 이미지에서 네 번째 값이 잘려서 안 보였음(DATA_INSIGHT로 추정). 확인 후 추가할 것.


class PlanStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "활성"
    REPLACED = "REPLACED", "재설정됨"
    CANCELED = "CANCELED", "취소됨"
    COMPLETED = "COMPLETED", "완료"


# LLM 호출 1회의 입력/출력 원본 로그
class AIPlanRun(BaseModel):
    """
    ERD: ai_plan_runs. LLM 호출 원본 로그(입력/출력 스냅샷).

    reference_sessions: IA 18번 "AI 추천 로직" 입력 5개 중 daily_context_id/pc_usage_patterns
    두 개만 컬럼으로 있고 "이전 수행 데이터"를 가리킬 컬럼이 없어서 추가함.
    sessions_app.Session을 참조하는데, sessions_app이 이미 plans(recovery_slot_id)를
    참조하고 있어서 plans ↔ sessions_app이 서로를 아는 구조가 된다. 문자열 참조라
    마이그레이션 자체는 문제없이 도는데, "의존성 한 방향" 원칙은 이 필드 때문에 깨진다.

    pc_usage_patterns: 기존엔 digital_state.DigitalDataEntry FK 하나였는데, Digital State가
    "요일×시간대 패턴"(여러 행)으로 바뀌면서 M2M으로 교체함. "오늘 요일"에 해당하는 패턴이
    있으면 그 날의 시간대별 데이터를 반영해 하루치 슬롯을 한 번에 생성하고, 없으면 오늘의 상황
    기반으로 다음 휴식 1개만 추천한다(다른 요일 패턴이 있어도 오늘 요일이 없으면 단건 모드).
    서비스 레이어에서 분기할 예정 — 그 분기 로직 자체는 아직 구현 안 함.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="ai_plan_runs")
    daily_context = models.ForeignKey(
        "context.DailyContext", on_delete=models.CASCADE, related_name="ai_plan_runs"
    )
    pc_usage_patterns = models.ManyToManyField(
        "digital_state.PcUsagePattern",
        blank=True,
        related_name="ai_plan_runs",
        help_text="비어있으면 오늘의 상황 기반 단건 추천, 있으면 패턴 기반 하루치 일괄 추천",
    )
    reference_sessions = models.ManyToManyField(
        "sessions_app.Session",
        blank=True,
        related_name="referenced_in_ai_plan_runs",
        help_text="이 추천을 생성할 때 참고한 이전 수행 기록(세션)들. 세션 피드백까지 필요하면 별도 필드 추가 필요.",
    )
    model_name = models.CharField(max_length=100)
    input_snapshot_json = models.JSONField()
    output_snapshot_json = models.JSONField()

    class Meta:
        ordering = ["-created_at"]


# 하루치 휴식 일정의 상위 컨테이너(사용자·날짜당 1건)
class RecoveryPlan(BaseModel):
    """
    ERD: recovery_plans. 이제 전체 컬럼 확인됨.

    overall_reason / data_source_summary는 ai_insights와 겹치는 부분이 있어서 확인 필요.
    - overall_reason: Home 화면에 바로 보여줄 요약 추천 이유로 보임 (ai_insights.body는
      09번 AI Insight 화면들의 상세 설명 — 화면이 다르면 중복 아니라 의도된 분리일 수 있음)
    - data_source_summary: IA 3번 섹션 예시 문구("오늘의 상황만 입력 → ...", "디지털 사용 패턴을
      바탕으로 → ...")를 담는 사람이 읽는 문장으로 추정. ai_insights.data_sources_json은
      같은 정보를 구조화된 리스트로 담음 — 형식만 다르고 내용은 같을 수 있어서 확인 필요.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="recovery_plans")
    daily_context = models.ForeignKey(
        "context.DailyContext", on_delete=models.CASCADE, related_name="recovery_plans"
    )
    ai_plan_run = models.ForeignKey(AIPlanRun, on_delete=models.SET_NULL, null=True, related_name="recovery_plans")
    plan_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.ACTIVE)
    overall_reason = models.TextField(blank=True)
    data_source_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-plan_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "plan_date"],
                condition=Q(status="ACTIVE"),
                name="unique_active_plan_per_user_date",
            )
        ]

    def __str__(self):
        return f"RecoveryPlan({self.user_id}, {self.plan_date})"


# RecoveryPlan에 속한 개별 휴식 타임슬롯
class RecoverySlot(BaseModel):
    """
    ERD: recovery_slots.
    ai_reason 컬럼은 이번에 제거함 — ai_insights(recovery_slot_id로 연결)로 일원화.
    """

    recovery_plan = models.ForeignKey(RecoveryPlan, on_delete=models.CASCADE, related_name="slots")
    sequence_no = models.PositiveSmallIntegerField()
    recommended_at = models.DateTimeField()
    scheduled_at = models.DateTimeField(null=True, blank=True)
    user_changed_at = models.DateTimeField(null=True, blank=True)
    interval_minutes = models.PositiveIntegerField(null=True, blank=True)
    repeat_rule = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=SlotStatus.choices, default=SlotStatus.RECOMMENDED)

    class Meta:
        ordering = ["recovery_plan", "sequence_no"]
        constraints = [
            models.UniqueConstraint(fields=["recovery_plan", "sequence_no"], name="unique_slot_sequence")
        ]

    @property
    def effective_time(self):
        return self.user_changed_at or self.scheduled_at or self.recommended_at

    def __str__(self):
        return f"RecoverySlot(plan={self.recovery_plan_id}, #{self.sequence_no})"


# RecoverySlot에 대한 알림 발송 기록
class Notification(BaseModel):
    """ERD: notifications. 실제 발송 인프라(서비스워커/구독관리)는 별도 확인 필요."""

    recovery_slot = models.ForeignKey(RecoverySlot, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.PENDING
    )


# AI 추천/판단에 대한 설명 텍스트 모음
class AIInsight(BaseModel):
    """
    ERD: ai_insights.
    recovery_slots.ai_reason / routine_instances.ai_reason이 없어졌으니,
    AI 추천/판단에 대한 설명 텍스트는 전부 여기로 모인다.
    """

    recovery_plan = models.ForeignKey(RecoveryPlan, on_delete=models.CASCADE, related_name="insights")
    recovery_slot = models.ForeignKey(
        RecoverySlot, on_delete=models.CASCADE, null=True, blank=True, related_name="insights"
    )
    routine_instance = models.ForeignKey(
        "routines.RoutineInstance", on_delete=models.CASCADE, null=True, blank=True, related_name="insights"
    )
    insight_type = models.CharField(max_length=30, choices=InsightType.choices)
    body = models.TextField()
    data_sources_json = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]
