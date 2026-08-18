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
    # MISSED(놓침)는 삭제함 — 추천 시간이 지나도 사용자가 언제든 세션을 시작할 수 있는
    # 정책이라 "놓쳐서 시작 불가"를 나타내는 상태 자체가 필요 없음.


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
    DATA_INSIGHT = "DATA_INSIGHT", "데이터 인사이트"  # IA 09-3 "Data Insight" 섹션과 매칭해서 확정


class PlanStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "활성"
    REPLACED = "REPLACED", "재설정됨"
    CANCELED = "CANCELED", "취소됨"
    COMPLETED = "COMPLETED", "완료"


# LLM 호출 1회의 입력/출력 원본 로그
class AIPlanRun(BaseModel):
    """
    ERD: ai_plan_runs. LLM 호출 원본 로그(입력/출력 스냅샷).

    reference_sessions(Session M2M), pc_usage_patterns(PcUsagePattern M2M)는 둘 다 제거함.
    이유 1(의존성 방향): reference_sessions는 sessions_app.Session을 참조하는데,
    sessions_app이 이미 plans(recovery_slot_id)를 참조하고 있어서 plans ↔ sessions_app이
    서로를 아는 구조가 됨(문자열 참조라 마이그레이션 자체는 도는데 "의존성 한 방향" 원칙은
    깨짐).
    이유 2(데이터 유실): pc_usage_patterns는 PUT /digital-state/patterns/bulk/가
    delete-then-create 방식이라, 사용자가 패턴을 수정하는 순간 on_delete=CASCADE로 과거
    AIPlanRun과의 M2M 연결이 조용히 끊어짐. AIPlanRun의 목적 자체가 "그 당시 뭘 보고
    추천했는지" 기록하는 것이라, 변경 가능한 DB row를 참조하는 대신 아래
    input_snapshot_json에 당시 값을 그대로 스냅샷으로 저장한다.
    예: {"previous_sessions": [...], "previous_feedback": [...],
         "pc_usage_patterns": [{"day_of_week": "MON", ...}]}
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="ai_plan_runs")
    daily_context = models.ForeignKey(
        "context.DailyContext", on_delete=models.CASCADE, related_name="ai_plan_runs"
    )
    model_name = models.CharField(max_length=100)
    input_snapshot_json = models.JSONField()
    output_snapshot_json = models.JSONField()

    class Meta:
        ordering = ["-created_at"]


# 하루치 휴식 일정의 상위 컨테이너(사용자·날짜당 1건)
class RecoveryPlan(BaseModel):
    """
    ERD: recovery_plans.

    overall_reason / data_source_summary는 ai_insights와 겹쳐서 제거함(ai_reason을
    ai_insights로 합쳤을 때와 같은 논리). 플랜 전체 단위 설명이 필요하면 AIInsight를
    recovery_plan만 걸고(recovery_slot/routine_instance는 null) 만들면 된다 —
    overall_reason은 insight_type=RECOMMENDATION_REASON 정도로, data_source_summary는
    data_sources_json으로 표현.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="recovery_plans")
    daily_context = models.ForeignKey(
        "context.DailyContext", on_delete=models.CASCADE, related_name="recovery_plans"
    )
    ai_plan_run = models.ForeignKey(AIPlanRun, on_delete=models.SET_NULL, null=True, related_name="recovery_plans")
    plan_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.ACTIVE)

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
