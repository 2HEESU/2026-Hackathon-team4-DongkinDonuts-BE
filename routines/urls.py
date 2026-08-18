from django.urls import path

from .views import ActivityTypeListView

app_name = "routines"

urlpatterns = [
    path(
        "activity-types/",
        ActivityTypeListView.as_view(),
        name="activity-type-list",
    ),
]