import uuid

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import User, UserSettings

DEVICE_CODE_HEADER = "HTTP_X_DEVICE_CODE"  # "X-Device-Code" 헤더의 request.META 키


class DeviceCodeAuthentication(BaseAuthentication):
    """
    로그인 없는 익명 사용자 식별.

    프론트가 X-Device-Code 헤더로 UUID를 보내면 그 값을 그대로 User.id로 써서
    조회하거나 없으면 새로 만든다(get_or_create). 그래서 별도의 "회원가입"
    엔드포인트가 필요 없다 — 이 인증 클래스가 모든 요청에서 자동으로 처리한다.

    - 헤더 자체가 없으면: 인증을 시도하지 않고 None 반환 (AnonymousUser로 진행,
      막을지는 각 view의 permission에서 결정)
    - 헤더는 있는데 UUID 형식이 아니면: 401 (AuthenticationFailed)
    """

    def authenticate(self, request):
        raw_value = request.META.get(DEVICE_CODE_HEADER)
        if not raw_value:
            return None

        try:
            device_id = uuid.UUID(raw_value)
        except (ValueError, AttributeError, TypeError):
            raise AuthenticationFailed("X-Device-Code 헤더 값이 올바른 UUID 형식이 아닙니다.")

        user, _ = User.objects.get_or_create(id=device_id)
        # User가 새로 생겼든 예전부터 있었든, UserSettings가 항상 존재하도록 보장한다.
        # (get_or_create라서 이미 있으면 그냥 넘어가고, 없을 때만 만듦 — 기존 User인데
        # Settings만 누락된 경우까지 복구됨)
        UserSettings.objects.get_or_create(user=user)
        return (user, None)

    def authenticate_header(self, request):
        # 이게 없으면 AuthenticationFailed가 403으로 내려감(DRF 기본 동작). 401이 맞는
        # 상황이라 non-empty 값을 반환해서 401로 나가게 한다.
        return "X-Device-Code"
