from django.urls import path

from .views import ActivityTypeListView, RoutineInstanceDetailView

app_name = "routines"

urlpatterns = [
    path(
        "activity-types/",
        ActivityTypeListView.as_view(),
        name="activity-type-list",
    ),
    path(
        "instances/<uuid:id>/",
        RoutineInstanceDetailView.as_view(),
        name="routine-instance-detail",
    ),
]