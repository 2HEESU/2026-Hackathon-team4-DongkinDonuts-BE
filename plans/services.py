from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Max, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from context.models import NextActivityPlan, UserContextSnapshot
from context.utils import today_for_user
from digital_state.models import DayOfWeek, PcUsagePattern
from sessions_app.models import Session, SessionFeedback, SessionStatus

from .models import (
    Notification,
    NotificationKind,
    NotificationStatus,
    PlanStatus,
    RecoveryPlan,
    RecoverySlot,
    SlotNotificationBasis,
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
MAX_POLICY_RECOMMENDED_TIMES = 12
PREVIOUS_SESSION_FREQUENCY_LOOKBACK_DAYS = 30
PREVIOUS_SESSION_FREQUENCY_MIN_COUNT = 3
FREQUENCY_CLUSTER_TOLERANCE_MINUTES = 30
MAX_PREVIOUS_SESSION_FREQUENCY_TIMES = 2
NOTIFICATION_RESPONSE_GRACE_MINUTES = 10


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


def notification_basis_for_plan(plan):
    return SlotNotificationBasis.SNAPSHOT


def get_next_open_slot(plan):
    return (
        plan.slots.filter(status__in=OPEN_SLOT_STATUSES)
        .annotate(effective_at=Coalesce("user_changed_at", "scheduled_at", "recommended_at"))
        .order_by("effective_at", "sequence_no")
        .first()
    )


def get_runnable_slot(plan):
    started_slot = (
        plan.slots.filter(status=SlotStatus.STARTED)
        .annotate(effective_at=Coalesce("user_changed_at", "scheduled_at", "recommended_at"))
        .order_by("effective_at", "sequence_no")
        .first()
    )
    return started_slot or get_next_open_slot(plan)


def get_next_slot_for_user(user):
    expire_unanswered_recovery_slots(user=user)
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


def get_runnable_slot_for_user(user):
    expire_unanswered_recovery_slots(user=user)
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
    return get_runnable_slot(plan)


def build_notification_message(slot):
    return f"{slot.effective_time:%H:%M} 회복 세션을 시작할 시간입니다."


def build_reengagement_message(scheduled_at):
    return f"{scheduled_at:%H:%M}에 짧은 회복 루틴을 다시 시작해볼까요?"


def notification_user_filter(user):
    return Q(user=user) | Q(user__isnull=True, recovery_slot__recovery_plan__user=user)


def pending_notifications_for_user(user):
    return Notification.objects.filter(status=NotificationStatus.PENDING).filter(notification_user_filter(user))


def cancel_pending_reengagement_notifications(*, user):
    return Notification.objects.filter(
        user=user,
        kind=NotificationKind.REENGAGEMENT,
        status=NotificationStatus.PENDING,
    ).update(status=NotificationStatus.CANCELED, updated_at=timezone.now())


def first_slot_for_reengagement(reference_slot):
    plan = reference_slot.recovery_plan
    return (
        RecoverySlot.objects.filter(recovery_plan__user=plan.user, recovery_plan__plan_date=plan.plan_date)
        .annotate(effective_at=Coalesce("user_changed_at", "scheduled_at", "recommended_at"))
        .order_by("effective_at", "sequence_no")
        .first()
    )


def schedule_reengagement_notification_if_needed(*, user, reference_slot):
    if pending_notifications_for_user(user).exists():
        return None

    source_slot = first_slot_for_reengagement(reference_slot)
    if source_slot is None:
        return None

    scheduled_at = source_slot.effective_time + timedelta(days=7)
    now = timezone.now()
    while scheduled_at <= now:
        scheduled_at += timedelta(days=7)

    return Notification.objects.create(
        user=user,
        recovery_slot=None,
        kind=NotificationKind.REENGAGEMENT,
        message=build_reengagement_message(scheduled_at),
        scheduled_at=scheduled_at,
        data_json={
            "source_recovery_slot": str(source_slot.id),
            "source_plan_date": str(source_slot.recovery_plan.plan_date),
            "url": "/",
        },
    )


def sync_slot_notification(slot):
    """
    슬롯 알림 설정을 Notification 발신 대기 목록과 맞춘다.

    Notification은 실제 발송 이력/대기 항목이고, RecoverySlot.notification_enabled는 사용자가
    해당 슬롯에 알림을 켰는지의 설정값이다.
    """

    pending_notifications = slot.notifications.filter(
        kind=NotificationKind.RECOVERY_SLOT,
        status=NotificationStatus.PENDING,
    )
    if slot.status not in OPEN_SLOT_STATUSES or not slot.notification_enabled:
        pending_notifications.update(status=NotificationStatus.CANCELED)
        return None

    cancel_pending_reengagement_notifications(user=slot.recovery_plan.user)
    notification = pending_notifications.order_by("-created_at").first()
    if notification is None:
        return Notification.objects.create(
            user=slot.recovery_plan.user,
            recovery_slot=slot,
            kind=NotificationKind.RECOVERY_SLOT,
            message=build_notification_message(slot),
            scheduled_at=slot.effective_time,
        )

    notification.user = slot.recovery_plan.user
    notification.message = build_notification_message(slot)
    notification.scheduled_at = slot.effective_time
    notification.save(update_fields=["user", "message", "scheduled_at", "updated_at"])
    return notification


def _slot_effective_time_annotation():
    return Coalesce("user_changed_at", "scheduled_at", "recommended_at")


def _open_slots_for_plan(plan, *, notification_basis=None):
    queryset = RecoverySlot.objects.select_for_update().filter(
        recovery_plan=plan,
        status__in=OPEN_SLOT_STATUSES,
    )
    if notification_basis is not None:
        queryset = queryset.filter(notification_basis=notification_basis)
    return queryset.annotate(effective_at=_slot_effective_time_annotation())


def _cancel_open_slots(slots):
    canceled_slots = []
    for slot in slots:
        if slot.status not in OPEN_SLOT_STATUSES:
            continue
        slot.status = SlotStatus.CANCELED
        slot.save(update_fields=["status", "updated_at"])
        sync_slot_notification(slot)
        canceled_slots.append(slot)
    return canceled_slots


@transaction.atomic
def expire_unanswered_recovery_slots(*, user=None, now=None):
    now = now or timezone.now()
    deadline = now - timedelta(minutes=NOTIFICATION_RESPONSE_GRACE_MINUTES)
    queryset = RecoverySlot.objects.select_for_update().filter(
        status__in=OPEN_SLOT_STATUSES,
        notifications__kind=NotificationKind.RECOVERY_SLOT,
        notifications__status=NotificationStatus.SENT,
        notifications__sent_at__lte=deadline,
    )
    if user is not None:
        queryset = queryset.filter(recovery_plan__user=user)

    slots = list(
        queryset.exclude(sessions__isnull=False)
        .distinct()
        .annotate(effective_at=_slot_effective_time_annotation())
        .order_by("effective_at", "sequence_no")
    )
    return _cancel_open_slots(slots)


def _minute_floor(value):
    return value.replace(second=0, microsecond=0)


def recommend_next_reset_time(next_activity_plan=None, base_time=None, context_snapshot=None):
    """
    다음 회복 슬롯 시각을 계산하는 정책 기반 기본값.

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


def _activity_window_end(next_activity_plan, base_time):
    expected_minutes = getattr(next_activity_plan, "expected_activity_minutes", None)
    if not expected_minutes:
        return None

    started_at = getattr(next_activity_plan, "created_at", None) or base_time
    return _minute_floor(started_at) + timedelta(minutes=expected_minutes)


def _activity_interval_times(*, base_time, end_time, interval, max_slots):
    if end_time is None:
        return [base_time + interval]

    if end_time <= base_time:
        return [base_time + interval]

    times = []
    candidate = base_time + interval
    while candidate <= end_time and len(times) < max_slots:
        times.append(candidate)
        candidate += interval

    if not times:
        times.append(_minute_floor(end_time))
    return times


def _local_datetime(value):
    if timezone.is_aware(value):
        return timezone.localtime(value)
    return value


def _minute_of_day(value):
    return value.hour * 60 + value.minute


def _pc_usage_pattern_hour_keys(user):
    return set(
        PcUsagePattern.objects.filter(user=user, is_used=True).values_list(
            "day_of_week",
            "hour",
        )
    )


def _matches_pc_usage_pattern(value, pattern_keys):
    local_value = _local_datetime(value)
    return (WEEKDAY_TO_DAY_OF_WEEK[local_value.weekday()], local_value.hour) in pattern_keys


def is_within_pc_usage_pattern(user, value):
    """
    value(datetime)가 사용자의 PC 사용 패턴 블록(요일+시간대) 안에 들어가는지 확인한다.
    AI가 자율적으로 정한 recommended_at을 서버에서 검증할 때 씀 — 패턴을 하나도
    안 넣은 사용자는 애초에 검증할 블록이 없으므로 항상 False.
    """
    pattern_keys = _pc_usage_pattern_hour_keys(user)
    if not pattern_keys:
        return False
    return _matches_pc_usage_pattern(value, pattern_keys)


def _today_pattern_hours(user):
    today_day_of_week = today_day_of_week_for_user(user)
    return set(
        PcUsagePattern.objects.filter(
            user=user,
            day_of_week=today_day_of_week,
            is_used=True,
        ).values_list("hour", flat=True)
    )


def _top_frequency_minute_clusters(minutes, max_clusters):
    remaining = sorted(minutes)
    clusters = []

    while remaining and len(clusters) < max_clusters:
        best_cluster = []
        best_average = 0

        for anchor in remaining:
            cluster = [
                minute
                for minute in remaining
                if abs(minute - anchor) <= FREQUENCY_CLUSTER_TOLERANCE_MINUTES
            ]
            average = sum(cluster) / len(cluster)
            if len(cluster) > len(best_cluster) or (
                len(cluster) == len(best_cluster) and average < best_average
            ):
                best_cluster = cluster
                best_average = average

        if len(best_cluster) < PREVIOUS_SESSION_FREQUENCY_MIN_COUNT:
            break

        clusters.append(
            {
                "minute": min(23 * 60 + 59, max(0, round(best_average))),
                "count": len(best_cluster),
            }
        )
        for minute in best_cluster:
            remaining.remove(minute)

    clusters.sort(key=lambda item: (-item["count"], item["minute"]))
    return clusters[:max_clusters]


def _previous_session_frequency_times(*, user, base_time, max_slots):
    pattern_keys = _pc_usage_pattern_hour_keys(user)
    today_hours = _today_pattern_hours(user)
    if not pattern_keys or not today_hours:
        return []

    since = base_time - timedelta(days=PREVIOUS_SESSION_FREQUENCY_LOOKBACK_DAYS)
    sessions = (
        Session.objects.filter(
            user=user,
            status=SessionStatus.COMPLETED,
            started_at__gte=since,
        )
        .exclude(started_at__isnull=True)
        .order_by("-started_at")
    )

    session_minutes = [
        _minute_of_day(_local_datetime(session.started_at))
        for session in sessions
        if _matches_pc_usage_pattern(session.started_at, pattern_keys)
    ]
    frequent_clusters = _top_frequency_minute_clusters(session_minutes, max_slots)

    plan_date = today_for_user(user)
    times = []
    for cluster in frequent_clusters:
        minute_of_day = cluster["minute"]
        hour = minute_of_day // 60
        minute = minute_of_day % 60
        if hour not in today_hours:
            continue
        candidate = datetime.combine(plan_date, time(hour=hour, minute=minute))
        if candidate <= base_time:
            continue
        times.append(candidate)

    return sorted(times)


def _merge_recommended_slot(slots_by_time, *, recommended_at, notification_basis, reason, data_sources):
    key = _minute_floor(recommended_at)
    existing = slots_by_time.get(key)
    if existing is None:
        slots_by_time[key] = {
            "recommended_at": key,
            "notification_basis": notification_basis,
            "reason": reason,
            "data_sources": list(data_sources),
        }
        return

    if notification_basis == SlotNotificationBasis.FREQUENCY:
        existing["notification_basis"] = SlotNotificationBasis.FREQUENCY
    if reason and reason not in existing["reason"]:
        existing["reason"] = f"{existing['reason']} {reason}".strip()
    for source in data_sources:
        if source not in existing["data_sources"]:
            existing["data_sources"].append(source)


def _slot_input_time_key(slot_input):
    recommended_at = slot_input.get("recommended_at")
    return _minute_floor(recommended_at) if recommended_at else None


def _append_slot_input(slot_inputs, slot_input):
    key = _slot_input_time_key(slot_input)
    if key is None:
        slot_inputs.append(slot_input)
        return

    for existing in slot_inputs:
        if _slot_input_time_key(existing) != key:
            continue
        if slot_input.get("notification_basis") == SlotNotificationBasis.FREQUENCY:
            existing["notification_basis"] = SlotNotificationBasis.FREQUENCY
        if "notification_enabled" in slot_input and "notification_enabled" not in existing:
            existing["notification_enabled"] = slot_input["notification_enabled"]
        return

    slot_inputs.append(slot_input)


def build_policy_recommended_slots(
    *,
    user,
    context_snapshot=None,
    next_activity_plan=None,
    base_time=None,
    max_slots=MAX_POLICY_RECOMMENDED_TIMES,
):
    """상태 기반 스냅샷 슬롯과 빈도 기반 슬롯을 함께 계산한다."""

    base_time = _minute_floor(base_time or timezone.now())
    policy_context = _context_from_inputs(context_snapshot, next_activity_plan)
    interval_minutes = recovery_interval_minutes_for_context(policy_context)
    interval = timedelta(minutes=interval_minutes)
    slots_by_time = {}

    activity_end = _activity_window_end(next_activity_plan, base_time)
    for recommended_at in _activity_interval_times(
        base_time=base_time,
        end_time=activity_end,
        interval=interval,
        max_slots=max_slots,
    ):
        _merge_recommended_slot(
            slots_by_time,
            recommended_at=recommended_at,
            notification_basis=SlotNotificationBasis.SNAPSHOT,
            reason="이후 활동 시간 동안 현재 상태에 맞춘 회복 간격으로 배치했습니다.",
            data_sources=["context_snapshot", "next_activity_plan", "time_policy"],
        )

    remaining_slots = max(0, min(MAX_PREVIOUS_SESSION_FREQUENCY_TIMES, max_slots - len(slots_by_time)))
    if remaining_slots:
        for recommended_at in _previous_session_frequency_times(
            user=user,
            base_time=base_time,
            max_slots=remaining_slots,
        ):
            _merge_recommended_slot(
                slots_by_time,
                recommended_at=recommended_at,
                notification_basis=SlotNotificationBasis.FREQUENCY,
                reason="주간 PC 사용 패턴과 최근 회복 세션 기록이 함께 몰린 시간대에 배치했습니다.",
                data_sources=["pc_usage_patterns", "previous_sessions", "time_policy"],
            )

    slots = sorted(slots_by_time.values(), key=lambda item: item["recommended_at"])
    return slots[:max_slots]


def build_policy_recommended_times(
    *,
    user,
    context_snapshot=None,
    next_activity_plan=None,
    base_time=None,
    max_slots=MAX_POLICY_RECOMMENDED_TIMES,
):
    return [
        slot["recommended_at"]
        for slot in build_policy_recommended_slots(
            user=user,
            context_snapshot=context_snapshot,
            next_activity_plan=next_activity_plan,
            base_time=base_time,
            max_slots=max_slots,
        )
    ]


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
        "context_snapshot": (
            str(next_activity_plan.context_snapshot_id)
            if next_activity_plan.context_snapshot_id
            else None
        ),
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
    recommended_slots=None,
    notification_enabled=True,
    ai_plan_run=None,
):
    """
    오늘 active RecoveryPlan을 새로 만든다.

    기존 active plan은 REPLACED로 닫고 새 plan을 만든다.

    recommended_times는 기존 호출부 호환용이고, 슬롯마다 알림 basis를 지정해야 하는 정책 생성
    흐름은 recommended_slots를 사용한다.
    """

    validate_context_inputs(user, context_snapshot, next_activity_plan)

    plan_date = today_for_user(user)
    now = timezone.now()
    active_plans = list(
        RecoveryPlan.objects.select_for_update().filter(
            user=user,
            plan_date=plan_date,
            status=PlanStatus.ACTIVE,
        )
    )
    preserved_frequency_slot_inputs = []
    for active_plan in active_plans:
        for slot in _open_slots_for_plan(
            active_plan,
            notification_basis=SlotNotificationBasis.FREQUENCY,
        ).order_by("effective_at", "sequence_no"):
            if slot.effective_time and slot.effective_time >= now:
                preserved_frequency_slot_inputs.append(
                    {
                        "recommended_at": slot.effective_time,
                        "notification_basis": SlotNotificationBasis.FREQUENCY,
                        "notification_enabled": slot.notification_enabled,
                    }
                )
        _cancel_open_slots(
            _open_slots_for_plan(active_plan).order_by("effective_at", "sequence_no")
        )
        active_plan.status = PlanStatus.REPLACED
        active_plan.save(update_fields=["status", "updated_at"])

    generation_snapshot = build_plan_generation_snapshot(user, context_snapshot, next_activity_plan)
    plan = RecoveryPlan.objects.create(
        user=user,
        ai_plan_run=ai_plan_run,
        plan_date=plan_date,
        generation_snapshot_json=generation_snapshot,
    )

    slot_inputs = list(recommended_slots or [])
    if not slot_inputs:
        slot_inputs = [
            {
                "recommended_at": recommended_at,
                "notification_basis": notification_basis_for_plan(plan),
            }
            for recommended_at in list(recommended_times or [])
        ]
    if not slot_inputs:
        slot_inputs = [
            {
                "recommended_at": None,
                "notification_basis": notification_basis_for_plan(plan),
            }
        ]
    for slot_input in preserved_frequency_slot_inputs:
        _append_slot_input(slot_inputs, slot_input)

    for slot_input in slot_inputs:
        create_recovery_slot(
            plan=plan,
            context_snapshot=context_snapshot,
            next_activity_plan=next_activity_plan,
            recommended_at=slot_input.get("recommended_at"),
            notification_enabled=slot_input.get("notification_enabled", notification_enabled),
            notification_basis=slot_input.get("notification_basis") or notification_basis_for_plan(plan),
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
    notification_basis=None,
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
    notification_basis = notification_basis or notification_basis_for_plan(locked_plan)
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
        notification_basis=notification_basis,
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

    이후 활동은 현재 활성 구간 기준으로 하나만 존재할 수 있으므로, 열린 스냅샷 기반 슬롯은
    모두 닫고 새 이후 활동 시간 안에서 다시 배치한다. 빈도 기반 슬롯은 독립 알림이라 유지한다.
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
        if slot_to_replace.notification_basis != SlotNotificationBasis.SNAPSHOT:
            raise ValidationError("스냅샷 기반 회복 슬롯만 이후 활동으로 다시 설정할 수 있습니다.")
    else:
        slot_to_replace = (
            _open_slots_for_plan(plan, notification_basis=SlotNotificationBasis.SNAPSHOT)
            .order_by("effective_at", "sequence_no")
            .first()
        )

    snapshot_slots = _open_slots_for_plan(
        plan,
        notification_basis=SlotNotificationBasis.SNAPSHOT,
    ).order_by("effective_at", "sequence_no")
    _cancel_open_slots(snapshot_slots)

    if recommended_at is not None:
        replacement_slots = [
            {
                "recommended_at": recommended_at,
                "notification_basis": SlotNotificationBasis.SNAPSHOT,
            }
        ]
    else:
        replacement_slots = [
            slot
            for slot in build_policy_recommended_slots(
                user=user,
                context_snapshot=context_snapshot,
                next_activity_plan=next_activity_plan,
                base_time=timezone.now(),
            )
            if slot["notification_basis"] == SlotNotificationBasis.SNAPSHOT
        ]

    if not replacement_slots:
        replacement_slots = [{"recommended_at": None, "notification_basis": SlotNotificationBasis.SNAPSHOT}]

    created_slots = []
    for slot_input in replacement_slots:
        created_slots.append(
            create_recovery_slot(
                plan=plan,
                context_snapshot=context_snapshot,
                next_activity_plan=next_activity_plan,
                recommended_at=slot_input.get("recommended_at"),
                notification_enabled=notification_enabled,
                notification_basis=SlotNotificationBasis.SNAPSHOT,
                ai_plan_run=ai_plan_run,
            )
        )

    return created_slots[0]


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
        notification_basis=SlotNotificationBasis.SNAPSHOT,
        ai_plan_run=ai_plan_run,
    )


@transaction.atomic
def set_slot_notification(*, slot, enabled, repeat_rule=""):
    slot.notification_enabled = enabled
    slot.repeat_rule = repeat_rule if enabled else ""
    slot.save(update_fields=["notification_enabled", "repeat_rule", "updated_at"])
    sync_slot_notification(slot)
    if not enabled:
        schedule_reengagement_notification_if_needed(
            user=slot.recovery_plan.user,
            reference_slot=slot,
        )
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


def _open_snapshot_slots_for_user(user):
    return (
        RecoverySlot.objects.select_for_update()
        .select_related("recovery_plan")
        .filter(
            recovery_plan__user=user,
            recovery_plan__plan_date=today_for_user(user),
            recovery_plan__status=PlanStatus.ACTIVE,
            notification_basis=SlotNotificationBasis.SNAPSHOT,
            status__in=OPEN_SLOT_STATUSES,
        )
        .annotate(effective_at=_slot_effective_time_annotation())
    )


@transaction.atomic
def cancel_snapshot_slots_before(*, user, before, exclude_slot=None):
    queryset = _open_snapshot_slots_for_user(user).filter(effective_at__lt=before)
    if exclude_slot is not None:
        queryset = queryset.exclude(id=exclude_slot.id)

    slots = list(queryset.order_by("effective_at", "sequence_no"))
    for slot in slots:
        slot.status = SlotStatus.CANCELED
        slot.save(update_fields=["status", "updated_at"])
        sync_slot_notification(slot)
    return slots


@transaction.atomic
def cancel_next_snapshot_slot_for_reentry(*, user, now=None):
    now = now or timezone.now()
    slot = _open_snapshot_slots_for_user(user).filter(effective_at__gt=now).order_by("effective_at", "sequence_no").first()
    if slot is None:
        return None
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


@transaction.atomic
def cleanup_nearby_pattern_notifications_on_entry(*, user, current_time=None, threshold_minutes=30):
    """
    [진입 시점 알림 삭제 정책]
    사용자 서비스 진입 시점(current_time)과 가장 가깝고 && 일정 시간(threshold_minutes) 이상
    차이 나지 않는 해당 PC 사용 패턴 블록의 빈도 기반 알림들을 CANCELED(삭제/취소) 처리한다.
    """
    now = current_time or timezone.now()
    threshold = timedelta(minutes=threshold_minutes)

    open_slots = RecoverySlot.objects.filter(
        recovery_plan__user=user,
        recovery_plan__plan_date=today_for_user(user),
        status__in=OPEN_SLOT_STATUSES,
    ).select_related("recovery_plan")

    canceled_slots = []
    for slot in open_slots:
        slot_time = slot.effective_time
        if slot_time and abs((slot_time - now).total_seconds()) <= threshold.total_seconds():
            slot.status = SlotStatus.CANCELED
            slot.save(update_fields=["status", "updated_at"])
            sync_slot_notification(slot)
            canceled_slots.append(slot)

    return canceled_slots