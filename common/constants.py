from django.db import models


class CameraPermissionStatus(models.TextChoices):
    """
    sessions_app.Session에서 씀(세션 시작 시점의 카메라 권한 스냅샷).
    원래 accounts.UserSettings에도 있었는데, 실제 브라우저 권한과 무관해서 DB에 둘 의미가
    없어 제거함 — 지금은 common에 있을 이유가 약하지만(단일 앱만 참조), 마이그레이션
    비용 대비 실익이 적어 이동은 보류.
    """

    UNKNOWN = "UNKNOWN", "확인 전"
    GRANTED = "GRANTED", "허용"
    DENIED = "DENIED", "거부"
    PROMPT = "PROMPT", "요청중"
