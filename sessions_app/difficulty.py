from .models import DifficultyFeedback, Session, SessionStatus


FRONTEND_ACTIVITY_BASE_IDS = {
    "SHIFT_EYE_RELAX": "eye-blink",
    "SHIFT_EYE_BLINK": "eye-blink",
    "EYE_BLINK": "eye-blink",
    "eye-blink": "eye-blink",
    "SHIFT_EYE_TRACKING": "eye-tracking",
    "EYE_TRACKING": "eye-tracking",
    "eye-tracking": "eye-tracking",
    "SHIFT_BODY_STRETCH": "neck-stretch",
    "SHIFT_NECK_STRETCH": "neck-stretch",
    "NECK_STRETCH": "neck-stretch",
    "neck-stretch": "neck-stretch",
    "SHIFT_SHOULDER_PMR": "shoulder-pmr",
    "SHOULDER_PMR": "shoulder-pmr",
    "shoulder-pmr": "shoulder-pmr",
    "SHIFT_FOCUS_SWITCH": "focus-pinch",
    "SHIFT_FOCUS_PINCH": "focus-pinch",
    "FOCUS_PINCH": "focus-pinch",
    "focus-pinch": "focus-pinch",
    "SHIFT_DROWSY_WAKE": "wakeup-sunrise",
    "SHIFT_WAKEUP_SUNRISE": "wakeup-sunrise",
    "WAKEUP_SUNRISE": "wakeup-sunrise",
    "wakeup-sunrise": "wakeup-sunrise",
}

DIFFICULTY_KEY_BY_LEVEL = {
    1: "low",
    2: "medium",
    3: "high",
}

DIFFICULTY_LEVEL_BY_KEY = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "하": 1,
    "중": 2,
    "상": 3,
}

MIN_FRONTEND_DIFFICULTY_LEVEL = 1
DEFAULT_FRONTEND_DIFFICULTY_LEVEL = 2
MAX_FRONTEND_DIFFICULTY_LEVEL = 3


def frontend_base_id_for_activity(activity_code):
    return FRONTEND_ACTIVITY_BASE_IDS.get(activity_code)


def activity_codes_for_frontend_base_id(base_id):
    return [
        activity_code
        for activity_code, candidate_base_id in FRONTEND_ACTIVITY_BASE_IDS.items()
        if candidate_base_id == base_id
    ]


def _clamp_frontend_level(level):
    return min(
        MAX_FRONTEND_DIFFICULTY_LEVEL,
        max(MIN_FRONTEND_DIFFICULTY_LEVEL, level),
    )


def normalize_frontend_difficulty_level(value, default=DEFAULT_FRONTEND_DIFFICULTY_LEVEL):
    if value is None:
        return default

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in DIFFICULTY_LEVEL_BY_KEY:
            return DIFFICULTY_LEVEL_BY_KEY[normalized]
        try:
            value = int(normalized)
        except ValueError:
            return default

    if isinstance(value, bool):
        return default

    try:
        return _clamp_frontend_level(int(value))
    except (TypeError, ValueError):
        return default


def frontend_difficulty_key(level):
    return DIFFICULTY_KEY_BY_LEVEL[
        normalize_frontend_difficulty_level(level)
    ]


def _session_completed_difficulty_level(session):
    metrics = session.metrics if isinstance(session.metrics, dict) else {}
    return normalize_frontend_difficulty_level(
        metrics.get("difficulty")
        or metrics.get("difficulty_level")
        or metrics.get("difficultyLevel")
    )


def _adjust_difficulty_level(completed_level, difficulty_feedback):
    if difficulty_feedback == DifficultyFeedback.TOO_EASY:
        return _clamp_frontend_level(completed_level + 1)

    if difficulty_feedback == DifficultyFeedback.A_BIT_HARD:
        return _clamp_frontend_level(completed_level - 1)

    return _clamp_frontend_level(completed_level)


def recommended_frontend_difficulty_for_routine(routine_instance, user=None):
    base_id = frontend_base_id_for_activity(routine_instance.activity_id)
    if base_id is None:
        return None

    user = user or routine_instance.recovery_slot.recovery_plan.user
    activity_codes = activity_codes_for_frontend_base_id(base_id)
    latest_session = (
        Session.objects.filter(
            user=user,
            activity_id__in=activity_codes,
            status=SessionStatus.COMPLETED,
            recovery_slot__feedback__difficulty_feedback__isnull=False,
            recovery_slot__feedback__skipped=False,
        )
        .exclude(recovery_slot_id=routine_instance.recovery_slot_id)
        .select_related("recovery_slot__feedback")
        .order_by("-ended_at", "-started_at", "-created_at")
        .first()
    )

    if latest_session is None:
        level = DEFAULT_FRONTEND_DIFFICULTY_LEVEL
    else:
        level = _adjust_difficulty_level(
            _session_completed_difficulty_level(latest_session),
            latest_session.recovery_slot.feedback.difficulty_feedback,
        )

    return {
        "base_id": base_id,
        "level": level,
        "key": frontend_difficulty_key(level),
    }
