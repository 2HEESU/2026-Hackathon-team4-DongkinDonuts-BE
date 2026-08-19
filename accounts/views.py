from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from common.mixins import EnvelopeMixin

from .serializers import UserSerializer, UserSettingsSerializer


class UserMeView(EnvelopeMixin, generics.RetrieveUpdateAPIView):
    """GET/PATCH /accounts/users/me/ — 내 프로필 조회/수정. pk 없이 request.user를 그대로 씀."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class UserSettingsMeView(EnvelopeMixin, generics.RetrieveUpdateAPIView):
    """GET/PATCH /accounts/settings/me/ — 내 설정 조회/수정."""

    serializer_class = UserSettingsSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user.settings
