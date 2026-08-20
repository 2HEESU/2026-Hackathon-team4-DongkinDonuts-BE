from django.urls import path

from .views import (
    PcUsagePatternAnalysisView,
    PcUsagePatternBulkUpdateView,
    PcUsagePatternListView,
    PcUsagePatternStatusView,
    RecentSessionActivityAnalysisView,
)

app_name = "digital_state"

urlpatterns = [
    path("patterns/bulk/", PcUsagePatternBulkUpdateView.as_view(), name="pattern-bulk-update"),
    path("patterns/", PcUsagePatternListView.as_view(), name="pattern-list"),
    path("patterns/analysis/", PcUsagePatternAnalysisView.as_view(), name="pattern-analysis"),
    path(
        "patterns/analysis/recent-sessions/",
        RecentSessionActivityAnalysisView.as_view(),
        name="pattern-analysis-recent-sessions",
    ),
    path("patterns/status/", PcUsagePatternStatusView.as_view(), name="pattern-status"),
]
