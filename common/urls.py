from django.urls import path

from .views import ActivityTagListView, StateOptionListView

app_name = "common"

urlpatterns = [
    path("activity-tags/", ActivityTagListView.as_view(), name="activity-tag-list"),
    path("state-options/", StateOptionListView.as_view(), name="state-option-list"),
]
