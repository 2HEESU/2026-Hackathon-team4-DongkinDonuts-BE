from context.utils import today_for_user

from .models import DayOfWeek, PcUsagePattern

DAY_ORDER = [
    DayOfWeek.MON,
    DayOfWeek.TUE,
    DayOfWeek.WED,
    DayOfWeek.THU,
    DayOfWeek.FRI,
    DayOfWeek.SAT,
    DayOfWeek.SUN,
]

DAY_LABELS = {
    DayOfWeek.MON: "월",
    DayOfWeek.TUE: "화",
    DayOfWeek.WED: "수",
    DayOfWeek.THU: "목",
    DayOfWeek.FRI: "금",
    DayOfWeek.SAT: "토",
    DayOfWeek.SUN: "일",
}

TOTAL_WEEKLY_CELLS = 7 * 24


def format_hour_range(start_hour, end_hour):
    return f"{start_hour:02d}:00 ~ {end_hour:02d}:00"


def group_consecutive_hours(hours):
    if not hours:
        return []

    sorted_hours = sorted(hours)
    ranges = []
    start = previous = sorted_hours[0]

    for hour in sorted_hours[1:]:
        if hour == previous + 1:
            previous = hour
            continue
        ranges.append({"start_hour": start, "end_hour": previous + 1, "label": format_hour_range(start, previous + 1)})
        start = previous = hour

    ranges.append({"start_hour": start, "end_hour": previous + 1, "label": format_hour_range(start, previous + 1)})
    return ranges


def summarize_day_pattern(day_usage_counts):
    max_count = max(day_usage_counts.values(), default=0)
    if max_count == 0:
        return {"label": "없음", "days": [], "usage_hours": 0}

    days = [day for day in DAY_ORDER if day_usage_counts.get(day, 0) == max_count]
    label = "평소" if len(days) == len(DAY_ORDER) else ", ".join(DAY_LABELS[day] for day in days)
    return {
        "label": label,
        "days": [{"day_of_week": day, "label": DAY_LABELS[day]} for day in days],
        "usage_hours": max_count,
    }


def summarize_time_pattern(hour_usage_counts):
    max_count = max(hour_usage_counts.values(), default=0)
    if max_count == 0:
        return {"label": "없음", "ranges": [], "usage_day_count": 0}

    max_hours = [hour for hour in range(24) if hour_usage_counts.get(hour, 0) == max_count]
    ranges = group_consecutive_hours(max_hours)
    return {
        "label": ", ".join(time_range["label"] for time_range in ranges),
        "ranges": ranges,
        "usage_day_count": max_count,
    }


def summarize_time_of_day_pattern(used_patterns):
    morning_count = sum(1 for pattern in used_patterns if pattern.hour < 12)
    afternoon_count = sum(1 for pattern in used_patterns if pattern.hour >= 12)

    if morning_count == 0 and afternoon_count == 0:
        return {"label": "없음", "segments": [], "counts": {"morning": 0, "afternoon": 0}}
    if morning_count == afternoon_count:
        label = "오전, 오후"
        segments = ["오전", "오후"]
    elif morning_count > afternoon_count:
        label = "오전"
        segments = ["오전"]
    else:
        label = "오후"
        segments = ["오후"]

    return {
        "label": label,
        "segments": segments,
        "counts": {"morning": morning_count, "afternoon": afternoon_count},
    }


def get_pattern_status(user):
    """
    '이 사용자가 PC 사용 패턴 맞춤 설정을 했는지'를 서버가 판단해서 내려준다.

    has_any_pattern/has_pattern_for_today 둘 다 is_used 값과 무관하게 row가 있는지만
    본다 — 모델 docstring 기준대로, "명시적으로 미사용 체크"도 "입력함"으로 쳐야 하고
    (is_used=False), row 자체가 없는 것과는 구분해야 하기 때문이다.

    - has_any_pattern: 온보딩 간소화 여부(맞춤 설정 완료 사용자인지) 판단용.
    - has_pattern_for_today: AI가 오늘 하루치 일정을 한 번에 만들지, 다음 휴식
      하나만 추천할지 분기하는 기준(모델 docstring에 명시된 기준 그대로).
    """
    has_any_pattern = PcUsagePattern.objects.filter(user=user).exists()

    today = today_for_user(user)
    today_day_of_week = DAY_ORDER[today.weekday()]
    has_pattern_for_today = PcUsagePattern.objects.filter(
        user=user, day_of_week=today_day_of_week
    ).exists()

    return {
        "has_any_pattern": has_any_pattern,
        "has_pattern_for_today": has_pattern_for_today,
    }


def analyze_pc_usage_patterns(user):
    patterns = list(PcUsagePattern.objects.filter(user=user, is_used=True).order_by("day_of_week", "hour"))
    selected_cells = [
        {
            "day_of_week": pattern.day_of_week,
            "day_label": DAY_LABELS[pattern.day_of_week],
            "hour": pattern.hour,
            "start_time": f"{pattern.hour:02d}:00",
            "end_time": f"{pattern.hour + 1:02d}:00",
        }
        for pattern in sorted(patterns, key=lambda item: (DAY_ORDER.index(item.day_of_week), item.hour))
    ]

    day_usage_counts = {day: 0 for day in DAY_ORDER}
    hour_usage_counts = {hour: 0 for hour in range(24)}
    for pattern in patterns:
        day_usage_counts[pattern.day_of_week] += 1
        hour_usage_counts[pattern.hour] += 1

    weekly_usage_hours = len(patterns)
    weekly_usage_days = [
        {"day_of_week": day, "label": DAY_LABELS[day], "usage_hours": day_usage_counts[day]}
        for day in DAY_ORDER
        if day_usage_counts[day] > 0
    ]

    return {
        "selected_cells": selected_cells,
        "weekly_pc_usage_hours": weekly_usage_hours,
        "weekly_pc_usage_days": weekly_usage_days,
        "weekly_pc_usage_day_count": len(weekly_usage_days),
        "weekly_activity_rate": {
            "selected_cells": weekly_usage_hours,
            "total_cells": TOTAL_WEEKLY_CELLS,
            "ratio": round(weekly_usage_hours / TOTAL_WEEKLY_CELLS, 4),
            "percent": round(weekly_usage_hours / TOTAL_WEEKLY_CELLS * 100, 2),
        },
        "most_used_patterns": {
            "day_pattern": summarize_day_pattern(day_usage_counts),
            "time_pattern": summarize_time_pattern(hour_usage_counts),
            "time_of_day_pattern": summarize_time_of_day_pattern(patterns),
        },
    }
