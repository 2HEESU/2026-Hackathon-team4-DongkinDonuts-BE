from django.urls import path

from .views import PcUsagePatternBulkUpdateView, PcUsagePatternListView

app_name = "digital_state"

urlpatterns = [
    path("patterns/bulk/", PcUsagePatternBulkUpdateView.as_view(), name="pattern-bulk-update"),
    path("patterns/", PcUsagePatternListView.as_view(), name="pattern-list"),
]
