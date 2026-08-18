from django.urls import path

from .views import PcUsagePatternAnalysisView, PcUsagePatternListReplaceView

app_name = "digital_state"
urlpatterns = [
    path("pc-usage-patterns/", PcUsagePatternListReplaceView.as_view(), name="pc-usage-pattern-list-replace"),
    path(
        "pc-usage-patterns/analysis/",
        PcUsagePatternAnalysisView.as_view(),
        name="pc-usage-pattern-analysis",
    ),
]
