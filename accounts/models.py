from django.db import models

from common.models import BaseModel


# 로그인 없는 익명 사용자 식별 정보
class User(BaseModel):
    """
    ERD: users
    로그인 없는 익명 사용자. BaseModel이 이미 UUID PK(id)를 제공하므로 별도 device_code
    필드를 두지 않는다 — 프론트가 생성한 UUID를 X-Device-Code 헤더로 보내면(프론트와 이미
    합의된 헤더 이름) 그 값을 그대로 User.id로 사용한다(get_or_create(id=header_value)).
    PK를 클라이언트가 직접 지정하는 구조라, view에서 헤더 값이 유효한 UUID 형식인지 먼저
    검증하고 아니면 400으로 거부해야 한다.
    """

    nickname = models.CharField(max_length=50, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Seoul")
    is_anonymous = models.BooleanField(default=True)

    def __str__(self):
        return self.nickname or str(self.id)[:12]


# 사용자별 알림/카메라 권한 설정
class UserSettings(BaseModel):
    """ERD: user_settings. 헤더 Settings(미개발) 화면에서 나중에 쓸 값들."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    notification_enabled = models.BooleanField(default=True)
    # camera_permission_status는 여기 두지 않는다 — 실제 브라우저 권한과 무관해서 DB에 저장할
    # 의미가 없음. 세션 시작 시점 스냅샷은 sessions_app.Session.camera_permission_status에 기록.

    def __str__(self):
        return f"UserSettings({self.user_id})"
