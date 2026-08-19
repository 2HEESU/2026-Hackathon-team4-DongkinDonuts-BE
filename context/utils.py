from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo


def today_for_user(user):
    """
    user.timezone(예: "Asia/Seoul") 기준의 '오늘' 날짜를 계산한다.
    settings.USE_TZ=False라서 django timezone.now()는 서버 TIME_ZONE 설정에만
    묶여있어 유저별 timezone을 반영 못 한다 — 그래서 UTC now를 직접 변환한다.
    """
    now_utc = datetime.now(dt_timezone.utc)
    return now_utc.astimezone(ZoneInfo(user.timezone)).date()
