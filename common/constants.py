from django.db import models


class CameraPermissionStatus(models.TextChoices):
    """accounts.UserSettings, sessions_app.Session 양쪽에서 공용으로 씀."""

    UNKNOWN = "UNKNOWN", "확인 전"
    GRANTED = "GRANTED", "허용"
    DENIED = "DENIED", "거부"
    PROMPT = "PROMPT", "요청중"
