from django.urls import path

from .views import (
    ActiveSessionView,
    SessionAbortView,
    SessionCompleteView,
    SessionDetailView,
    SessionResetView,
    SessionStartView,
)

app_name = "sessions_app"

urlpatterns = [
    path(
        "",
        SessionStartView.as_view(),
        name="session-start",
    ),
    path(
        "active/",
        ActiveSessionView.as_view(),
        name="session-active",
    ),
    path(
        "<uuid:id>/reset/",
        SessionResetView.as_view(),
        name="session-reset",
    ),
    path(
        "<uuid:id>/abort/",
        SessionAbortView.as_view(),
        name="session-abort",
    ),
    path(
        "<uuid:id>/complete/",
        SessionCompleteView.as_view(),
        name="session-complete",
    ),
    path(
        "<uuid:id>/",
        SessionDetailView.as_view(),
        name="session-detail",
    ),
]