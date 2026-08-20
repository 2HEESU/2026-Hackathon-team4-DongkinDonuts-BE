import json

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from common.models import StateOption
from context.models import NextActivityPlan, UserContextSnapshot, UserContextSnapshotState
from context.utils import today_for_user
from digital_state.models import PcUsagePattern
from digital_state.services import DAY_LABELS, DAY_ORDER, analyze_pc_usage_patterns
from routines.models import ActivityType, RoutineInstance, RoutineInstanceStatus, StageType
from sessions_app.models import Session, SessionFeedback

from .models import AIInsight, AIPlanRun, InsightType
from .openai_client import create_structured_response
from .services import (
    build_policy_recommended_times,
    create_or_replace_today_plan,
    get_today_pc_usage_patterns,
    recommend_next_reset_time,
    recovery_time_policy_for_context,
)


STAGE_SEQUENCE = {
    StageType.BRAIN_WAKE: 1,
    StageType.BRAIN_SHIFT: 2,
    StageType.BRAIN_RESET: 3,
}

COMMON_STAGE_TYPES = [StageType.BRAIN_WAKE, StageType.BRAIN_RESET]
RECENT_COMMON_ACTIVITY_LIMIT = 10

RECOVERY_PLAN_SCHEMA = {
    "name": "brainfit_recovery_plan",
    "description": "Brainfit 하루 회복 세션 추천 계획",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "slots", "insights"],
        "properties": {
            "summary": {"type": "string"},
            "slots": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "recommended_at",
                        "interval_minutes",
                        "reason",
                        "shift_recommendation",
                    ],
                    "properties": {
                        "recommended_at": {
                            "type": "string",
                            "description": "YYYY-MM-DDTHH:MM:SS 형식의 Asia/Seoul 기준 추천 시각",
                        },
                        "interval_minutes": {
                            "type": ["integer", "null"],
                            "minimum": 5,
                            "maximum": 240,
                        },
                        "reason": {"type": "string"},
                        "shift_recommendation": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "activity_code",
                                "difficulty_level",
                                "planned_duration_sec",
                                "reason",
                            ],
                            "properties": {
                                "activity_code": {
                                    "type": "string",
                                    "description": "shift_activity_catalog에 있는 Brain Shift activity code",
                                },
                                "difficulty_level": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 5,
                                },
                                "planned_duration_sec": {
                                    "type": "integer",
                                    "minimum": 10,
                                    "maximum": 600,
                                },
                                "reason": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "insights": {
                "type": "array",
                "minItems": 0,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["insight_type", "body", "data_sources"],
                    "properties": {
                        "insight_type": {
                            "type": "string",
                            "enum": [
                                InsightType.TODAY_ANALYSIS,
                                InsightType.RECOMMENDATION_REASON,
                                InsightType.DATA_INSIGHT,
                            ],
                        },
                        "body": {"type": "string"},
                        "data_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 8,
                        },
                    },
                },
            },
        },
    },
}

SYSTEM_PROMPT = """
너는 Brainfit의 회복 세션 플래너다.
사용자의 현재 상태, 이후 활동 계획, 이전 수행 기록과 피드백, 이전 상태 빈도, PC 사용 패턴을
함께 보고 오늘의 회복 세션 추천 시간과 Brain Shift 맞춤 활동을 만든다.

규칙:
- 하나의 회복 세션은 서버에서 항상 Brain Wake → Brain Shift → Brain Reset 3단계로 생성된다.
- Brain Wake와 Brain Reset은 모든 상태에서 공통으로 제공되며 서버가 선택한다.
- 개인화는 Brain Shift에만 적용한다. shift_recommendation은 반드시 shift_activity_catalog에 있는
  activity_code 중 하나를 골라야 한다.
- [필수 제약 조건] 모든 recommended_at 추천 시각은 사용자가 선택한 pc_usage_patterns (PC 사용 시간대 블록) 범위 내부여야 한다. PC를 사용하지 않는 시간대에는 절대 알림을 생성하지 않는다.
- [AI 자율 판단] PC 사용 밀집 구간과 과거 세션/상태 빈도를 고려하여 알림의 수량(slots 개수)과 가장 피로도가 누적될 것으로 예상되는 최적의 발송 시각을 자유롭게 판단하여 추천한다.
- recommended_at은 current_time 이후, plan_date 당일, YYYY-MM-DDTHH:MM:SS 형식으로 작성한다.
- difficulty_level은 사용자의 상태와 피드백을 반영하되 활동의 난이도 범위 안에서 정한다.
""".strip()


def _isoformat(value):
    return value.isoformat() if value else None


def _latest_today_snapshot(user):
    return (
        UserContextSnapshot.objects.filter(user=user, service_date=today_for_user(user))
        .order_by("-created_at")
        .first()
    )


def _latest_today_activity_plan(user, context_snapshot=None):
    queryset = NextActivityPlan.objects.filter(user=user, service_date=today_for_user(user))
    if context_snapshot is not None:
        contextual_plan = queryset.filter(context_snapshot=context_snapshot).order_by("-created_at").first()
        if contextual_plan is not None:
            return contextual_plan
    return queryset.order_by("-created_at").first()


def resolve_generation_inputs(user, context_snapshot=None, next_activity_plan=None):
    if context_snapshot is None:
        context_snapshot = _latest_today_snapshot(user)
    if context_snapshot is None:
        raise ValidationError("오늘의 상태 스냅샷이 필요합니다.")

    if next_activity_plan is None:
        next_activity_plan = _latest_today_activity_plan(user, context_snapshot=context_snapshot)
    if next_activity_plan is None:
        raise ValidationError("오늘의 이후 활동 계획이 필요합니다.")
    if next_activity_plan.user_id != user.id:
        raise ValidationError("본인의 이후 활동 계획만 사용할 수 있습니다.")
    if context_snapshot.user_id != user.id:
        raise ValidationError("본인의 상태 스냅샷만 사용할 수 있습니다.")

    return context_snapshot, next_activity_plan


def _serialize_context_snapshot(context_snapshot):
    return {
        "id": str(context_snapshot.id),
        "service_date": str(context_snapshot.service_date),
        "note": context_snapshot.note,
        "state_options": [
            {
                "code": link.state_id,
                "label": link.state.label,
                "priority": link.priority,
                "default_difficulty": link.state.default_difficulty,
                "routine_direction": link.state.routine_direction,
            }
            for link in context_snapshot.state_links.select_related("state").order_by("priority")
        ],
        "created_at": _isoformat(context_snapshot.created_at),
    }


def _serialize_next_activity_plan(next_activity_plan):
    return {
        "id": str(next_activity_plan.id),
        "service_date": str(next_activity_plan.service_date),
        "expected_activity_minutes": next_activity_plan.expected_activity_minutes,
        "activity_tags": [
            {
                "code": link.activity_tag_id,
                "name": link.activity_tag.name,
                "category": link.activity_tag.category,
            }
            for link in next_activity_plan.activity_tag_links.select_related("activity_tag")
        ],
        "created_at": _isoformat(next_activity_plan.created_at),
    }


def _serialize_pc_usage_patterns(user):
    patterns = sorted(
        PcUsagePattern.objects.filter(user=user, is_used=True),
        key=lambda item: (DAY_ORDER.index(item.day_of_week), item.hour),
    )
    return [
        {
            "day_of_week": pattern.day_of_week,
            "day_label": DAY_LABELS[pattern.day_of_week],
            "hour": pattern.hour,
            "start_time": f"{pattern.hour:02d}:00",
            "end_time": f"{pattern.hour + 1:02d}:00",
        }
        for pattern in patterns
    ]


def _serialize_state_frequencies(user):
    counts = list(
        UserContextSnapshotState.objects.filter(context_snapshot__user=user)
        .values("state_id")
        .annotate(count=Count("state_id"))
        .order_by("-count", "state_id")[:10]
    )
    states = StateOption.objects.in_bulk([item["state_id"] for item in counts])
    return [
        {
            "code": item["state_id"],
            "label": states[item["state_id"]].label if item["state_id"] in states else item["state_id"],
            "count": item["count"],
        }
        for item in counts
    ]


def _serialize_previous_sessions(user):
    sessions = (
        Session.objects.filter(user=user)
        .select_related("activity", "recovery_slot")
        .order_by("-started_at")[:10]
    )
    return [
        {
            "id": str(session.id),
            "recovery_slot": str(session.recovery_slot_id),
            "activity_code": session.activity_id,
            "activity_name": session.activity.name,
            "stage_type": session.activity.stage_type,
            "started_at": _isoformat(session.started_at),
            "ended_at": _isoformat(session.ended_at),
            "duration_sec": session.duration_sec,
            "accuracy": session.accuracy,
            "status": session.status,
        }
        for session in sessions
    ]


def _serialize_previous_feedback(user):
    feedbacks = (
        SessionFeedback.objects.filter(user=user)
        .select_related("recovery_slot")
        .order_by("-created_at")[:10]
    )
    return [
        {
            "id": str(feedback.id),
            "recovery_slot": str(feedback.recovery_slot_id),
            "recovery_feeling": feedback.recovery_feeling,
            "difficulty_feedback": feedback.difficulty_feedback,
            "skipped": feedback.skipped,
            "created_at": _isoformat(feedback.created_at),
        }
        for feedback in feedbacks
    ]


def _serialize_activity(activity):
    return {
        "code": activity.code,
        "stage_type": activity.stage_type,
        "target_state": activity.target_state_id,
        "name": activity.name,
        "purpose": activity.purpose,
        "min_difficulty": activity.min_difficulty,
        "max_difficulty": activity.max_difficulty,
        "default_duration_sec": activity.default_duration_sec,
    }


def _serialize_activity_catalog():
    return [
        _serialize_activity(activity)
        for activity in ActivityType.objects.filter(is_active=True).order_by("stage_type", "code")
    ]


def _context_state_codes(context_snapshot):
    return list(context_snapshot.state_links.order_by("priority").values_list("state_id", flat=True))


def _shift_activities_for_context(context_snapshot):
    state_codes = _context_state_codes(context_snapshot)
    queryset = ActivityType.objects.filter(is_active=True, stage_type=StageType.BRAIN_SHIFT)
    if state_codes:
        activities = list(queryset.filter(target_state_id__in=state_codes))
        if activities:
            priority = {code: index for index, code in enumerate(state_codes)}
            return sorted(activities, key=lambda activity: (priority.get(activity.target_state_id, 999), activity.code))
    return list(queryset.filter(target_state__isnull=True).order_by("code"))


def _serialize_shift_activity_catalog(context_snapshot):
    return [_serialize_activity(activity) for activity in _shift_activities_for_context(context_snapshot)]


def build_ai_input_snapshot(user, context_snapshot, next_activity_plan):
    has_today_pattern = get_today_pc_usage_patterns(user).exists()
    mode = "WEEK_PATTERN_BATCH" if has_today_pattern else "SEQUENTIAL_NEXT_ONLY"
    return {
        "plan_date": str(today_for_user(user)),
        "current_time": _isoformat(timezone.now()),
        "timezone": getattr(user, "timezone", "Asia/Seoul"),
        "generation_mode": mode,
        "context_snapshot": _serialize_context_snapshot(context_snapshot),
        "next_activity_plan": _serialize_next_activity_plan(next_activity_plan),
        "previous_sessions": _serialize_previous_sessions(user),
        "previous_feedback": _serialize_previous_feedback(user),
        "previous_state_frequencies": _serialize_state_frequencies(user),
        "pc_usage_patterns": _serialize_pc_usage_patterns(user),
        "pc_usage_analysis": analyze_pc_usage_patterns(user),
        "time_policy": recovery_time_policy_for_context(context_snapshot),
        "activity_catalog": _serialize_activity_catalog(),
        "shift_activity_catalog": _serialize_shift_activity_catalog(context_snapshot),
        "routine_generation_policy": {
            "fixed_stage_order": [StageType.BRAIN_WAKE, StageType.BRAIN_SHIFT, StageType.BRAIN_RESET],
            "personalized_stage": StageType.BRAIN_SHIFT,
            "server_selected_common_stages": COMMON_STAGE_TYPES,
        },
    }


def build_input_messages(input_snapshot):
    return [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": json.dumps(input_snapshot, ensure_ascii=False),
                }
            ],
        },
    ]


def _safe_int(value, default=None, minimum=None, maximum=None):
    if value is None:
        return default
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        integer = max(minimum, integer)
    if maximum is not None:
        integer = min(maximum, integer)
    return integer


def _time_policy_reason(policy, raw_reason=None):
    state_intervals = policy.get("state_intervals") or []
    if state_intervals:
        selected_codes = set(policy.get("selected_state_codes") or [])
        selected_labels = [
            item["state_label"] for item in state_intervals if item["state_code"] in selected_codes
        ]
        if selected_labels:
            base_reason = (
                f"{', '.join(selected_labels)} 상태 기준 {policy['interval_minutes']}분 "
                "회복 타이머 정책을 적용했습니다."
            )
        else:
            base_reason = f"{policy['interval_minutes']}분 회복 타이머 정책을 적용했습니다."
    else:
        base_reason = f"기본 {policy['interval_minutes']}분 회복 타이머 정책을 적용했습니다."

    if raw_reason:
        return f"{base_reason} {raw_reason}"
    return base_reason


def normalize_ai_slots(ai_output, user, context_snapshot, next_activity_plan):
    now = timezone.now().replace(microsecond=0)
    has_today_pattern = get_today_pc_usage_patterns(user).exists()
    max_slots = 6 if has_today_pattern else 1
    policy = recovery_time_policy_for_context(context_snapshot)
    policy_times = build_policy_recommended_times(
        user=user,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        base_time=now,
        max_slots=max_slots,
    )
    raw_slots = ai_output.get("slots", [])
    normalized = []

    for index, recommended_at in enumerate(policy_times):
        raw_slot = raw_slots[index] if index < len(raw_slots) else {}
        normalized.append(
            {
                "recommended_at": recommended_at,
                "interval_minutes": policy["interval_minutes"],
                "reason": _time_policy_reason(policy, raw_slot.get("reason")),
                "shift_recommendation": raw_slot.get("shift_recommendation") or {},
            }
        )

    if not normalized:
        normalized.append(
            {
                "recommended_at": recommend_next_reset_time(
                    next_activity_plan,
                    base_time=now,
                    context_snapshot=context_snapshot,
                ).replace(microsecond=0),
                "interval_minutes": policy["interval_minutes"],
                "reason": _time_policy_reason(policy, "AI 응답에 유효한 추천 시간이 없어 보정했습니다."),
                "shift_recommendation": {},
            }
        )

    normalized.sort(key=lambda item: item["recommended_at"])
    return normalized[:max_slots]


def _create_plan_insights(plan, ai_output):
    summary = ai_output.get("summary")
    if summary:
        AIInsight.objects.create(
            recovery_plan=plan,
            insight_type=InsightType.RECOMMENDATION_REASON,
            body=summary,
            data_sources_json=["llm_summary"],
        )

    for insight in ai_output.get("insights", []):
        insight_type = insight.get("insight_type")
        if insight_type not in InsightType.values:
            insight_type = InsightType.DATA_INSIGHT
        body = insight.get("body")
        if not body:
            continue
        AIInsight.objects.create(
            recovery_plan=plan,
            insight_type=insight_type,
            body=body,
            data_sources_json=insight.get("data_sources", []),
        )


def _create_slot_insight(slot, reason):
    if not reason:
        return
    AIInsight.objects.create(
        recovery_plan=slot.recovery_plan,
        recovery_slot=slot,
        insight_type=InsightType.RECOMMENDATION_REASON,
        body=reason,
        data_sources_json=["llm_slot_reason"],
    )


def _active_stage_activities(stage_type):
    activities = list(ActivityType.objects.filter(is_active=True, stage_type=stage_type).order_by("code"))
    if not activities:
        raise ValidationError(f"{stage_type} 활동 카탈로그가 필요합니다.")
    return activities


def _recent_activity_codes(user, stage_type):
    return list(
        Session.objects.filter(user=user, activity__stage_type=stage_type)
        .order_by("-started_at")
        .values_list("activity_id", flat=True)[:RECENT_COMMON_ACTIVITY_LIMIT]
    )


def _select_common_activity(*, user, stage_type, used_codes=None, avoid_recent=False):
    used_codes = used_codes if used_codes is not None else set()
    activities = _active_stage_activities(stage_type)
    recent_codes = set(_recent_activity_codes(user, stage_type)) if avoid_recent else set()
    candidates = [
        activity
        for activity in activities
        if activity.code not in used_codes and activity.code not in recent_codes
    ]
    if not candidates:
        candidates = [activity for activity in activities if activity.code not in used_codes]
    if not candidates:
        candidates = activities

    activity = candidates[0]
    used_codes.add(activity.code)
    return activity


def _validate_recovery_activity_catalog(context_snapshot):
    _active_stage_activities(StageType.BRAIN_WAKE)
    _active_stage_activities(StageType.BRAIN_RESET)
    if not _shift_activities_for_context(context_snapshot):
        raise ValidationError("현재 상태에 맞는 Brain Shift 활동 카탈로그가 필요합니다.")


def _state_default_difficulty_map(context_snapshot):
    return {
        link.state_id: link.state.default_difficulty
        for link in context_snapshot.state_links.select_related("state")
    }


def _difficulty_for_activity(activity, requested_difficulty=None, default_difficulty=None):
    return _safe_int(
        requested_difficulty,
        default=default_difficulty or activity.min_difficulty,
        minimum=activity.min_difficulty,
        maximum=activity.max_difficulty,
    )


def _duration_for_activity(activity, requested_duration=None):
    return _safe_int(
        requested_duration,
        default=activity.default_duration_sec,
        minimum=10,
        maximum=600,
    )


def _select_shift_activity(context_snapshot, recommendation):
    activities = _shift_activities_for_context(context_snapshot)
    if not activities:
        raise ValidationError("현재 상태에 맞는 Brain Shift 활동 카탈로그가 필요합니다.")

    activity_by_code = {activity.code: activity for activity in activities}
    requested_activity = activity_by_code.get(recommendation.get("activity_code"))
    activity = requested_activity or activities[0]

    state_defaults = _state_default_difficulty_map(context_snapshot)
    default_difficulty = state_defaults.get(activity.target_state_id, activity.min_difficulty)
    if requested_activity:
        reason = recommendation.get("reason") or "현재 상태에 맞는 Brain Shift 활동입니다."
        data_sources = ["llm_shift_reason"]
    else:
        reason = "현재 상태에 맞는 Brain Shift 활동으로 보정했습니다."
        data_sources = ["server_shift_fallback"]

    return {
        "activity": activity,
        "sequence_no": STAGE_SEQUENCE[StageType.BRAIN_SHIFT],
        "difficulty_level": _difficulty_for_activity(
            activity,
            requested_difficulty=recommendation.get("difficulty_level"),
            default_difficulty=default_difficulty,
        ),
        "planned_duration_sec": _duration_for_activity(activity, recommendation.get("planned_duration_sec")),
        "reason": reason,
        "data_sources": data_sources,
    }


def _common_routine_spec(*, user, stage_type, used_codes, avoid_recent):
    activity = _select_common_activity(
        user=user,
        stage_type=stage_type,
        used_codes=used_codes,
        avoid_recent=avoid_recent,
    )
    return {
        "activity": activity,
        "sequence_no": STAGE_SEQUENCE[stage_type],
        "difficulty_level": _difficulty_for_activity(activity),
        "planned_duration_sec": activity.default_duration_sec,
        "reason": "",
        "data_sources": [],
    }


def _create_routine_instances(slot, context_snapshot, shift_recommendation, used_common_codes):
    routine_specs = [
        _common_routine_spec(
            user=slot.recovery_plan.user,
            stage_type=StageType.BRAIN_WAKE,
            used_codes=used_common_codes[StageType.BRAIN_WAKE],
            avoid_recent=True,
        ),
        _select_shift_activity(context_snapshot, shift_recommendation),
        _common_routine_spec(
            user=slot.recovery_plan.user,
            stage_type=StageType.BRAIN_RESET,
            used_codes=used_common_codes[StageType.BRAIN_RESET],
            avoid_recent=False,
        ),
    ]

    for index, spec in enumerate(sorted(routine_specs, key=lambda item: item["sequence_no"])):
        routine = RoutineInstance.objects.create(
            recovery_slot=slot,
            activity=spec["activity"],
            sequence_no=spec["sequence_no"],
            difficulty_level=spec["difficulty_level"],
            planned_duration_sec=spec["planned_duration_sec"],
            status=RoutineInstanceStatus.AVAILABLE if index == 0 else RoutineInstanceStatus.LOCKED,
            locked_until_previous_done=index != 0,
        )
        if spec["reason"] and spec["activity"].stage_type == StageType.BRAIN_SHIFT:
            AIInsight.objects.create(
                recovery_plan=slot.recovery_plan,
                recovery_slot=slot,
                routine_instance=routine,
                insight_type=InsightType.ROUTINE_REASON,
                body=spec["reason"],
                data_sources_json=spec["data_sources"],
            )


@transaction.atomic
def _persist_ai_plan(
    *,
    user,
    context_snapshot,
    next_activity_plan,
    input_snapshot,
    ai_output,
    raw_response,
    normalized_slots,
    notification_enabled,
):
    ai_run = AIPlanRun.objects.create(
        user=user,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        model_name=settings.OPENAI_MODEL,
        input_snapshot_json=input_snapshot,
        output_snapshot_json={"parsed": ai_output, "raw_response": raw_response},
    )
    plan = create_or_replace_today_plan(
        user=user,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        recommended_times=[slot["recommended_at"] for slot in normalized_slots],
        notification_enabled=notification_enabled,
        ai_plan_run=ai_run,
    )
    _create_plan_insights(plan, ai_output)

    slots = list(plan.slots.order_by("sequence_no"))
    used_common_codes = {stage_type: set() for stage_type in COMMON_STAGE_TYPES}
    for slot, ai_slot in zip(slots, normalized_slots):
        slot.interval_minutes = ai_slot["interval_minutes"]
        slot.save(update_fields=["interval_minutes", "updated_at"])
        _create_slot_insight(slot, ai_slot["reason"])
        _create_routine_instances(
            slot,
            context_snapshot,
            ai_slot["shift_recommendation"],
            used_common_codes,
        )

    return plan


def generate_ai_recovery_plan(
    *,
    user,
    context_snapshot=None,
    next_activity_plan=None,
    notification_enabled=True,
):
    context_snapshot, next_activity_plan = resolve_generation_inputs(
        user=user,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
    )
    _validate_recovery_activity_catalog(context_snapshot)
    input_snapshot = build_ai_input_snapshot(user, context_snapshot, next_activity_plan)
    ai_output, raw_response = create_structured_response(
        input_messages=build_input_messages(input_snapshot),
        schema=RECOVERY_PLAN_SCHEMA,
        model=settings.OPENAI_MODEL,
    )
    normalized_slots = normalize_ai_slots(ai_output, user, context_snapshot, next_activity_plan)
    return _persist_ai_plan(
        user=user,
        context_snapshot=context_snapshot,
        next_activity_plan=next_activity_plan,
        input_snapshot=input_snapshot,
        ai_output=ai_output,
        raw_response=raw_response,
        normalized_slots=normalized_slots,
        notification_enabled=notification_enabled,
    )
