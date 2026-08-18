from django.urls import path

from .views import DailyContextCreateView, DailyContextTodayView, DailyContextUpdateView

app_name = "context"

urlpatterns = [
    path("daily-contexts/today/", DailyContextTodayView.as_view(), name="daily-context-today"),
    path("daily-contexts/", DailyContextCreateView.as_view(), name="daily-context-create"),
    path("daily-contexts/<uuid:pk>/", DailyContextUpdateView.as_view(), name="daily-context-update"),
]
