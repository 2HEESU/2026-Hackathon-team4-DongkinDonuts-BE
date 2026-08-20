from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from common.models import StateOption

from .models import NextActivityPlan, UserContextSnapshotState
from .utils import today_for_user

DEFAULT_STATE_FREQUENCY_DAYS = 30


def get_state_frequency(user, days=DEFAULT_STATE_FREQUENCY_DAYS):
    """
    최근 days일간 사용자가 선택한 상태(StateOption)별 빈도를 집계한다.

    plans가 AI 회복 계획을 만들 때 "이 사용자가 어떤 상태를 자주 겪는지"로 루틴
    비중을 조정하는 근거로 쓴다(명세 18번 "이전 상태 기록(빈도로 중요도 부여)").
    원본 테이블(UserContextSnapshotState, priority 등)을 plans 쪽이 몰라도 되게
    여기서 캡슐화한다.

    활성 상태 카탈로그 전부를 포함해서 반환한다 — 한 번도 선택 안 한 상태도
    count=0으로 내려줘야 소비하는 쪽이 "데이터가 없다"와 "안 겪는다"를 구분할 수 있다.
    """
    since = today_for_user(user) - timedelta(days=days - 1)
    counts = {
        row["state_id"]: row["count"]
        for row in UserContextSnapshotState.objects.filter(
            context_snapshot__user=user,
            context_snapshot__service_date__gte=since,
        )
        .values("state_id")
        .annotate(count=Count("id"))
    }

    results = [
        {"code": state.code, "label": state.label, "count": counts.get(state.code, 0)}
        for state in StateOption.objects.filter(is_active=True)
    ]
    results.sort(key=lambda item: item["count"], reverse=True)
    return results


def get_current_valid_next_activity_plan(user, now=None):
    """
    오늘 사용자가 만든 이후 활동 중 아직 예상 활동 시간이 끝나지 않은 최신 계획을 반환한다.

    새 상태 점검이 들어와도 유효한 이후 활동이 있으면 활동 종류/시간과 그 활동에 붙은
    기존 상태 스냅샷을 유지해야 하므로, 생성 시각 + expected_activity_minutes를
    활동의 유효 구간으로 본다.
    """

    now = now or timezone.now()
    plans = (
        NextActivityPlan.objects.filter(
            user=user,
            service_date=today_for_user(user),
            expected_activity_minutes__isnull=False,
        )
        .select_related("context_snapshot")
        .order_by("-created_at")
    )

    for plan in plans:
        valid_until = plan.created_at + timedelta(minutes=plan.expected_activity_minutes)
        if valid_until > now:
            return plan
    return None
