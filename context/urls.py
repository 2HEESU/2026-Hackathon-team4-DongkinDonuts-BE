from django.urls import path

from .views import (
    NextActivityPlanCreateView,
    NextActivityPlanTodayView,
    NextActivityPlanUpdateView,
    UserContextSnapshotCreateView,
    UserContextSnapshotTodayView,
    UserContextSnapshotUpdateView,
)

app_name = "context"

urlpatterns = [
    path("context-snapshots/today/", UserContextSnapshotTodayView.as_view(), name="context-snapshot-today"),
    path("context-snapshots/", UserContextSnapshotCreateView.as_view(), name="context-snapshot-create"),
    path("context-snapshots/<uuid:pk>/", UserContextSnapshotUpdateView.as_view(), name="context-snapshot-update"),
    path("next-activity-plans/today/", NextActivityPlanTodayView.as_view(), name="next-activity-plan-today"),
    path("next-activity-plans/", NextActivityPlanCreateView.as_view(), name="next-activity-plan-create"),
    path("next-activity-plans/<uuid:pk>/", NextActivityPlanUpdateView.as_view(), name="next-activity-plan-update"),
]
