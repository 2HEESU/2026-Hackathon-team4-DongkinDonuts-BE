from django.db import models

from common.models import BaseModel


# 로그인 없는 익명 사용자 식별 정보
class User(BaseModel):
    """
    ERD: users
    로그인 없는 익명 사용자. BaseModel이 이미 UUID PK(id)를 제공하므로 별도 device_code
    필드를 두지 않는다 — 프론트가 생성한 UUID를 X-Device-Code 헤더로 보내면(프론트와 이미
    합의된 헤더 이름) 그 값을 그대로 User.id로 사용한다(get_or_create(id=header_value)).
    accounts.authentication.DeviceCodeAuthentication이 매 요청마다 이 처리를 하므로
    별도의 "회원가입" 엔드포인트는 필요 없다. 헤더 값이 유효한 UUID 형식이 아니면 401.

    is_anonymous 필드는 지웠다 — 로그인 기능을 아예 안 만들기로 확정해서 값이 영원히
    True로 고정되는 죽은 필드였음. 대신 아래 is_authenticated/is_anonymous는 진짜 필드가
    아니라 DRF가 request.user에 기대하는 인터페이스를 맞춰주기 위한 고정값 프로퍼티다
    (permission 체크 등에서 request.user.is_authenticated를 부르면 항상 True를 준다).
    """

    nickname = models.CharField(max_length=50, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Seoul")

    def __str__(self):
        return self.nickname or str(self.id)[:12]

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


# 사용자별 알림/카메라 권한 설정
class UserSettings(BaseModel):
    """ERD: user_settings. 헤더 Settings(미개발) 화면에서 나중에 쓸 값들."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    notification_enabled = models.BooleanField(default=True)
    # camera_permission_status는 여기 두지 않는다 — 실제 브라우저 권한과 무관해서 DB에 저장할
    # 의미가 없음. 세션 시작 시점 스냅샷은 sessions_app.Session.camera_permission_status에 기록.

    def __str__(self):
        return f"UserSettings({self.user_id})"
