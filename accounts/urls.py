from django.urls import path

from .views import UserMeView, UserSettingsMeView

app_name = "accounts"

urlpatterns = [
    path("users/me/", UserMeView.as_view(), name="user-me"),
    path("settings/me/", UserSettingsMeView.as_view(), name="user-settings-me"),
]
