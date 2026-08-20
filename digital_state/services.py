from datetime import timedelta

from django.utils import timezone

from context.utils import today_for_user
from sessions_app.models import Session, SessionStatus

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


class _HourOnlyCell:
    """summarize_time_of_day_pattern은 .hour 속성이 있는 객체 리스트를 받는데,
    PcUsagePattern 모델 인스턴스 대신 세션 기록에서 뽑은 시각을 넣어줄 때 쓰는
    가벼운 래퍼."""

    def __init__(self, hour):
        self.hour = hour


def analyze_recent_session_patterns(user, days=7):
    """
    '언제 PC를 쓸 것 같다'는 자기보고(PcUsagePattern 체크)가 아니라, 최근 `days`일간
    실제로 완료한 회복 세션 기록(Session.started_at)을 근거로 같은 형태의 분석
    결과를 만든다. 사용자가 미리 예정해둔 패턴보다, 실제로 회복 세션을 시작한
    시점이 훨씬 신뢰할 수 있는 신호라서 이걸로 대체한다.

    같은 (요일, 시) 조합에 세션이 여러 번 있어도 한 칸으로만 센다 — 자기보고
    버전(analyze_pc_usage_patterns)의 "이 요일 이 시간대엔 보통 활동한다"는
    의미와 동일한 형태를 유지해서, 프론트가 두 응답을 그대로 같은 컴포넌트에
    꽂아 쓸 수 있게 하기 위함이다.
    """
    since = timezone.now() - timedelta(days=days)

    sessions = Session.objects.filter(
        user=user,
        status=SessionStatus.COMPLETED,
        started_at__gte=since,
    )

    day_usage_counts = {day: 0 for day in DAY_ORDER}
    hour_usage_counts = {hour: 0 for hour in range(24)}
    seen_cells = set()
    selected_cells = []

    for session in sessions:
        # USE_TZ=False라서 started_at은 이미 로컬(Asia/Seoul) 벽시계 시각 그대로다.
        day_code = DAY_ORDER[session.started_at.weekday()]
        hour = session.started_at.hour
        cell_key = (day_code, hour)

        if cell_key in seen_cells:
            continue
        seen_cells.add(cell_key)

        day_usage_counts[day_code] += 1
        hour_usage_counts[hour] += 1
        selected_cells.append(
            {
                "day_of_week": day_code,
                "day_label": DAY_LABELS[day_code],
                "hour": hour,
                "start_time": f"{hour:02d}:00",
                "end_time": f"{hour + 1:02d}:00",
            }
        )

    selected_cells.sort(key=lambda item: (DAY_ORDER.index(item["day_of_week"]), item["hour"]))

    weekly_usage_hours = len(selected_cells)
    weekly_usage_days = [
        {"day_of_week": day, "label": DAY_LABELS[day], "usage_hours": day_usage_counts[day]}
        for day in DAY_ORDER
        if day_usage_counts[day] > 0
    ]

    return {
        "analysis_window_days": days,
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
            "time_of_day_pattern": summarize_time_of_day_pattern(
                [_HourOnlyCell(cell["hour"]) for cell in selected_cells]
            ),
        },
    }
