from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from context.models import NextActivityPlan, UserContextSnapshot
from context.utils import today_for_user
from digital_state.models import DayOfWeek, PcUsagePattern
from sessions_app.models import SessionFeedback

from .models import (
    Notification,
    NotificationStatus,
    PlanStatus,
    RecoveryPlan,
    RecoverySlot,
    SlotStatus,
    WebPushSubscription,
)

WEEKDAY_TO_DAY_OF_WEEK = {
    0: DayOfWeek.MON,
    1: DayOfWeek.TUE,
    2: DayOfWeek.WED,
    3: DayOfWeek.THU,
    4: DayOfWeek.FRI,
    5: DayOfWeek.SAT,
    6: DayOfWeek.SUN,
}

OPEN_SLOT_STATUSES = [
    SlotStatus.RECOMMENDED,
    SlotStatus.SCHEDULED,
    SlotStatus.CHANGED,
]

RECOVERY_INTERVAL_MINUTES_BY_STATE = {
    "EYE_TIRED": 20,
    "BODY_STIFF": 30,
    "LOW_FOCUS": 45,
    "SLEEPY": 30,
}
DEFAULT_RECOVERY_INTERVAL_MINUTES = 45
MAX_POLICY_RECOMMENDED_TIMES = 6


def today_day_of_week_for_user(user):
    today = today_for_user(user)
    return WEEKDAY_TO_DAY_OF_WEEK[today.weekday()]


def get_today_pc_usage_patterns(user):
    """오늘 요일에 대해 사용자가 명시 입력한 PC 패턴 rows를 시간순으로 반환한다."""

    return PcUsagePattern.objects.filter(
        user=user,
        day_of_week=today_day_of_week_for_user(user),
        is_used=True,
    ).order_by("hour")


def has_today_pc_usage_pattern(user):
    return get_today_pc_usage_patterns(user).exists()


def _context_from_inputs(context_snapshot=None, next_activity_plan=None):
    if context_snapshot is not None:
        return context_snapshot
    return getattr(next_activity_plan, "context_snapshot", None)


def _state_interval_items(context_snapshot):
    if context_snapshot is None:
        return []

    links = context_snapshot.state_links.select_related("state").order_by("priority")
    items = []
    for link in links:
        interval_minutes = RECOVERY_INTERVAL_MINUTES_BY_STATE.get(link.state_id)
        if interval_minutes is None:
            continue
        items.append(
            {
                "state_code": link.state_id,
                "state_label": link.state.label,
                "priority": link.priority,
                "interval_minutes": interval_minutes,
            }
        )
    return items


def recovery_time_policy_for_context(context_snapshot=None):
    """
    첨부 정책집의 상태별 타이머를 서버 기준값으로 계산한다.

    복수 상태가 들어오면 더 짧은 간격을 우선해 피로 누적을 막는다.
    """

    state_intervals = _state_interval_items(context_snapshot)
    if state_intervals:
        interval_minutes = min(item["interval_minutes"] for item in state_intervals)
        selected = [
            item for item in state_intervals if item["interval_minutes"] == interval_minutes
        ]
        return {
            "interval_minutes": interval_minutes,
            "basis": "selected_state_shortest_interval",
            "state_intervals": state_intervals,
            "selected_state_codes": [item["state_code"] for item in selected],
            "reason": "복수 상태 중 가장 짧은 권장 타이머 간격을 적용했습니다.",
        }

    return {
        "interval_minutes": DEFAULT_RECOVERY_INTERVAL_MINUTES,
        "basis": "default_focus_interval",
        "state_intervals": state_intervals,
        "selected_state_codes": [],
        "reason": "정책 매핑 상태가 없어 기본 집중 회복 간격을 적용했습니다.",
    }


def recovery_interval_minutes_for_context(context_snapshot=None):
    return recovery_time_policy_for_context(context_snapshot)["interval_minutes"]


def plan_has_today_pc_usage_pattern(plan):
    return bool(plan.generation_snapshot_json.get("has_today_pc_usage_pattern", False))


def get_next_open_slot(plan):
    return (
        plan.slots.filter(status__in=OPEN_SLOT_STATUSES)
        .annotate(effective_at=Coalesce("user_changed_at", "scheduled_at", "recommended_at"))
        .order_by("effective_at", "sequence_no")
        .first()
    )


def get_next_slot_for_user(user):
    plan = (
        RecoveryPlan.objects.filter(
            user=user,
            plan_date=today_for_user(user),
            status=PlanStatus.ACTIVE,
        )
        .prefetch_related("slots")
        .first()
    )
    if plan is None:
        return None
    return get_next_open_slot(plan)


def build_notification_message(slot):
    return f"{slot.effective_time:%H:%M} 회복 세션을 시작할 시간입니다."


def sync_slot_notification(slot):
    """
    슬롯 알림 설정을 Notification 발신 대기 목록과 맞춘다.

    Notification은 실제 발송 이력/대기 항목이고, RecoverySlot.notification_enabled는 사용자가
    해당 슬롯에 알림을 켰는지의 설정값이다.
    """

    pending_notifications = slot.notifications.filter(status=NotificationStatus.PENDING)
    if slot.status not in OPEN_SLOT_STATUSES or not slot.notification_enabled:
        pending_notifications.update(status=NotificationStatus.CANCELED)
        return None

    notification = pending_notifications.order_by("-created_at").first()
    if notification is None:
        return Notification.objects.create(
            recovery_slot=slot,
            message=build_notification_message(slot),
            scheduled_at=slot.effective_time,
        )

    notification.message = build_notification_message(slot)
    notification.scheduled_at = slot.effective_time
    notification.save(update_fields=["message", "scheduled_at", "updated_at"])
    return notification


def _minute_floor(value):
    return value.replace(second=0, microsecond=0)


def recommend_next_reset_time(next_activity_plan=None, base_time=None, context_snapshot=None):
    """
    AI 추천 전까지 쓰는 정책 기반 기본값.

    첨부 정책집 기준으로 현재 상태별 타이머 간격을 사용한다. 사용자가 시간을 직접
    지정하는 수동/예약 흐름은 view가 recommended_at/recommended_times를 명시 전달한다.
    """

    base_time = _minute_floor(base_time or timezone.now())
    policy_context = _context_from_inputs(context_snapshot, next_activity_plan)
    minutes = recovery_interval_minutes_for_context(policy_context)
    return base_time + timedelta(minutes=minutes)


def _datetime_at_hour(date_value, hour):
    if hour >= 24:
        return datetime.combine(date_value + timedelta(days=1), time.min)
    return datetime.combine(date_value, time(hour=hour))


def _today_pc_usage_windows(user):
    patterns = list(get_today_pc_usage_patterns(user))
    if not patterns:
        return []

    plan_date = today_for_user(user)
    hours = sorted({pattern.hour for pattern in patterns})
    windows = []
    start_hour = previous_hour = hours[0]
    for hour in hours[1:]:
        if hour == previous_hour + 1:
            previous_hour = hour
            continue
        windows.append(
            (_datetime_at_hour(plan_date, start_hour), _datetime_at_hour(plan_date, previous_hour + 1))
        )
        start_hour = previous_hour = hour
    windows.append(
        (_datetime_at_hour(plan_date, start_hour), _datetime_at_hour(plan_date, previous_hour + 1))
    )
    return windows


def build_policy_recommended_times(
    *,
    user,
    context_snapshot=None,
    next_activity_plan=None,
    base_time=None,
    max_slots=MAX_POLICY_RECOMMENDED_TIMES,
):
    """
    상태별 타이머 정책을 실제 추천 시각 목록으로 펼친다.

    오늘 PC 사용 패턴이 있으면 남은 사용 구간 안에 정책 간격으로 최대 max_slots개를
    배치하고, 없으면 다음 세션 1개만 만든다.
    """

    base_time = _minute_floor(base_time or timezone.now())
    policy_context = _context_from_inputs(context_snapshot, next_activity_plan)
    interval_minutes = recovery_interval_minutes_for_context(policy_context)
    interval = timedelta(minutes=interval_minutes)
    fallback_time = base_time + interval

    if not has_today_pc_usage_pattern(user):
        return [fallback_time]

    plan_date = today_for_user(user)
    recommended_times = []
    for start_at, end_at in _today_pc_usage_windows(user):
        if end_at <= base_time:
            continue
        candidate = max(start_at, base_time) + interval
        while (
            candidate <= end_at
            and candidate.date() == plan_date
            and len(recommended_times) < max_slots
        ):
            recommended_times.append(candidate)
            candidate += interval
        if len(recommended_times) >= max_slots:
            break

    return recommended_times or [fallback_time]


def build_plan_generation_snapshot(user, context_snapshot=None, next_activity_plan=None):
    """
    계획 생성 시점의 분기 근거를 불변 JSON으로 저장한다.

    RecoveryPlan/RecoverySlot에 PC 패턴 기반 여부 enum을 두지 않고도 이후 로직이 생성 당시의
    판단을 재사용할 수 있게 하는 최소 스냅샷이다.
    """

    today_patterns = list(get_today_pc_usage_patterns(user).values("day_of_week", "hour", "is_used"))
    pc_usage_pattern_count = PcUsagePattern.objects.filter(user=user, is_used=True).count()
    return {
        "service_date": str(today_for_user(user)),
        "has_today_pc_usage_pattern": bool(today_patterns),
        "has_pc_usage_pattern": pc_usage_pattern_count > 0,
        "pc_usage_pattern_count": pc_usage_pattern_count,
        "pc_usage_patterns": today_patterns,
        "time_policy": recovery_time_policy_for_context(context_snapshot),
        "context_snapshot": serialize_context_snapshot(context_snapshot),
        "next_activity_plan": serialize_next_activity_plan(next_activity_plan),
    }


def serialize_context_snapshot(context_snapshot):
    if context_snapshot is None:
        return None
    return {
        "id": str(context_snapshot.id),
        "state_options": list(
            context_snapshot.state_links.order_by("priority").values_list("state_id", flat=True)
        ),
        "note": context_snapshot.note,
        "created_at": context_snapshot.created_at.isoformat() if context_snapshot.created_at else None,
    }


def serialize_next_activity_plan(next_activity_plan):
    if next_activity_plan is None:
        return None
    return {
        "id": str(next_activity_plan.id),
        "activity_tags": list(next_activity_plan.activity_tag_links.values_list("activity_tag_id", flat=True)),
        "expected_activity_minutes": next_activity_plan.expected_activity_minutes,
        "created_at": next_activity_plan.created_at.isoformat() if next_activity_plan.created_at else None,
    }


def validate_context_inputs(user, context_snapshot=None, next_activity_plan=None):
    if context_snapshot is not None and context_snapshot.user_id != user.id:
        raise ValidationError("본인의 상태 스냅샷만 사용할 수 있습니다.")
    if next_activity_plan is not None and next_activity_plan.user_id != user.id:
        raise ValidationError("본인의 이후 활동 계획만 사용할 수 있습니다.")


@transaction.atomic
def create_or_replace_today_plan(
    *,
    user,
    context_snapshot=None,
    next_activity_plan=None,
    recommended_times=None,
    notification_enabled=True,
    ai_plan_run=None,
):
    """
    오늘 active RecoveryPlan을 새로 만든다.

    기존 active plan은 REPLACED로 닫고 새 plan을 만든다. PC 패턴이 없는 계획은 호출 한 번에
    하나의 RecoverySlot만 만든다. PC 패턴이 있는 계획은 recommended_times로 넘어온 하루치
    후보들을 그대로 슬롯화한다.
    """

    validate_context_inputs(user, context_snapshot, next_activity_plan)

    plan_date = today_for_user(user)
    RecoveryPlan.objects.filter(
        user=user,
        plan_date=plan_date,
        status=PlanStatus.ACTIVE,
    ).update(status=PlanStatus.REPLACED)

    generation_snapshot = build_plan_generation_snapshot(user, context_snapshot, next_activity_plan)
    plan = RecoveryPlan.objects.create(
        user=user,
        ai_plan_run=ai_plan_run,
        plan_date=plan_date,
        generation_snapshot_json=generation_snapshot,
    )

    times = list(recommended_times or [])
    if not times:
        times = [None]
    if not generation_snapshot["has_today_pc_usage_pattern"]:
        times = times[:1]

    for recommended_at in times:
        create_recovery_slot(
            plan=plan,
            context_snapshot=context_snapshot,
            next_activity_plan=next_activity_plan,
            recommended_at=recommended_at,
            notification_enabled=notification_enabled,
            ai_plan_run=ai_plan_run,
        )
    return plan


@transaction.atomic
def create_recovery_slot(
    *,
    plan,
    context_snapshot=None,
    next_activity_plan=None,
    recommended_at=None,
    notification_enabled=True,
    ai_plan_run=None,
):
    validate_context_inputs(plan.user, context_snapshot, next_activity_plan)

    locked_plan = RecoveryPlan.objects.select_for_update().get(id=plan.id)
    last_sequence = locked_plan.slots.aggregate(max_sequence=Max("sequence_no"))["max_sequence"] or 0
    generated_recommended_at = recommended_at is None
    if generated_recommended_at:
        recommended_at = recommend_next_reset_time(
            next_activity_plan,
            context_snapshot=context_snapshot,
        )
    slot = RecoverySlot.objects.create(
        recovery_plan=locked_plan,
        ai_plan_run=ai_plan_run,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        sequence_no=last_sequence + 1,
        recommended_at=recommended_at,
        interval_minutes=(
            recovery_interval_minutes_for_context(_context_from_inputs(context_snapshot, next_activity_plan))
            if generated_recommended_at
            else None
        ),
        notification_enabled=notification_enabled,
    )
    sync_slot_notification(slot)
    return slot


@transaction.atomic
def reset_next_activity_and_slot(
    *,
    user,
    target_slot=None,
    context_snapshot=None,
    next_activity_plan=None,
    recommended_at=None,
    notification_enabled=True,
    ai_plan_run=None,
):
    """
    '내 계획 다시 설정' 흐름.

    상태 스냅샷은 새로 만들지 않고 이후 활동 계획만 교체해도 된다. 하루에는 여러 이후 활동과
    여러 슬롯이 있을 수 있으므로 plan 전체가 아니라 대상 슬롯 하나만 취소한 뒤 새 슬롯을 만든다.
    target_slot이 없으면 가장 가까운 열린 슬롯을 대상으로 삼고, 열린 슬롯이 없으면 새 슬롯만 만든다.
    """

    validate_context_inputs(user, context_snapshot, next_activity_plan)
    plan = RecoveryPlan.objects.select_for_update().get(
        user=user,
        plan_date=today_for_user(user),
        status=PlanStatus.ACTIVE,
    )

    slot_to_replace = None
    if target_slot is not None:
        slot_to_replace = RecoverySlot.objects.select_for_update().get(id=target_slot.id, recovery_plan=plan)
        if slot_to_replace.status not in OPEN_SLOT_STATUSES:
            raise ValidationError("열려 있는 회복 슬롯만 다시 설정할 수 있습니다.")
    else:
        slot_to_replace = (
            RecoverySlot.objects.select_for_update()
            .filter(recovery_plan=plan, status__in=OPEN_SLOT_STATUSES)
            .annotate(effective_at=Coalesce("user_changed_at", "scheduled_at", "recommended_at"))
            .order_by("effective_at", "sequence_no")
            .first()
        )

    if slot_to_replace is not None:
        slot_to_replace.status = SlotStatus.CANCELED
        slot_to_replace.save(update_fields=["status", "updated_at"])
        sync_slot_notification(slot_to_replace)

    return create_recovery_slot(
        plan=plan,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        recommended_at=recommended_at,
        notification_enabled=notification_enabled,
        ai_plan_run=ai_plan_run,
    )


@transaction.atomic
def schedule_next_slot_after_completed_slot(
    *,
    completed_slot,
    context_snapshot=None,
    next_activity_plan=None,
    recommended_at=None,
    notification_enabled=True,
    ai_plan_run=None,
):
    """
    PC 패턴이 없는 순차 생성 흐름에서 세션 완료 후 다음 RecoverySlot을 1개 추가한다.

    생성 당시 PC 패턴이 있었던 plan은 이미 하루치 슬롯을 갖고 있으므로 새 슬롯을 만들지 않는다.
    """

    slot = RecoverySlot.objects.select_for_update().select_related("recovery_plan__user").get(
        id=completed_slot.id
    )
    if slot.status != SlotStatus.COMPLETED:
        slot.status = SlotStatus.COMPLETED
        slot.save(update_fields=["status", "updated_at"])

    plan = slot.recovery_plan
    if plan_has_today_pc_usage_pattern(plan):
        return None

    return create_recovery_slot(
        plan=plan,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        recommended_at=recommended_at,
        notification_enabled=notification_enabled,
        ai_plan_run=ai_plan_run,
    )


@transaction.atomic
def set_slot_notification(*, slot, enabled, repeat_rule=""):
    slot.notification_enabled = enabled
    slot.repeat_rule = repeat_rule if enabled else ""
    slot.save(update_fields=["notification_enabled", "repeat_rule", "updated_at"])
    sync_slot_notification(slot)
    return slot


@transaction.atomic
def schedule_slot_time(*, slot, scheduled_at):
    slot.user_changed_at = scheduled_at
    slot.status = SlotStatus.CHANGED
    slot.save(update_fields=["user_changed_at", "status", "updated_at"])
    sync_slot_notification(slot)
    return slot


@transaction.atomic
def cancel_slot(*, slot):
    slot.status = SlotStatus.CANCELED
    slot.save(update_fields=["status", "updated_at"])
    sync_slot_notification(slot)
    return slot


@transaction.atomic
def mark_notification_clicked(*, notification):
    notification.status = NotificationStatus.CLICKED
    notification.clicked_at = timezone.now()
    notification.save(update_fields=["status", "clicked_at", "updated_at"])
    return notification


@transaction.atomic
def submit_slot_feedback(*, slot, recovery_feeling, difficulty_feedback):
    feedback, _ = SessionFeedback.objects.update_or_create(
        recovery_slot=slot,
        defaults={
            "user": slot.recovery_plan.user,
            "recovery_feeling": recovery_feeling,
            "difficulty_feedback": difficulty_feedback,
            "skipped": False,
        },
    )
    if slot.status != SlotStatus.COMPLETED:
        slot.status = SlotStatus.COMPLETED
        slot.save(update_fields=["status", "updated_at"])
    sync_slot_notification(slot)
    return feedback


@transaction.atomic
def upsert_web_push_subscription(*, user, endpoint, p256dh, auth, user_agent=""):
    subscription, _ = WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": user_agent,
            "is_active": True,
            "last_seen_at": timezone.now(),
        },
    )
    return subscription


@transaction.atomic
def deactivate_web_push_subscription(*, subscription):
    subscription.is_active = False
    subscription.save(update_fields=["is_active", "updated_at"])
    return subscription
