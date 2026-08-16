from django.db import models

from common.constants import CameraPermissionStatus
from common.models import BaseModel


# 로그인 없는 익명 사용자 식별 정보
class User(BaseModel):
    """
    ERD: users
    로그인 없는 익명 사용자. device_code는 프론트가 생성해서(로컬스토리지 등) 매 요청마다
    헤더로 보내는 값이라고 가정한다 — 어떻게 만들고 보낼지는 프론트와 별도 확정 필요.
    """

    device_code = models.CharField(max_length=128, unique=True, db_index=True)
    nickname = models.CharField(max_length=50, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Seoul")
    is_anonymous = models.BooleanField(default=True)

    def __str__(self):
        return self.nickname or self.device_code[:12]


# 사용자별 알림/카메라 권한 설정
class UserSettings(BaseModel):
    """ERD: user_settings. 헤더 Settings(미개발) 화면에서 나중에 쓸 값들."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    notification_enabled = models.BooleanField(default=True)
    camera_permission_status = models.CharField(
        max_length=20, choices=CameraPermissionStatus.choices, default=CameraPermissionStatus.UNKNOWN
    )

    def __str__(self):
        return f"UserSettings({self.user_id})"
