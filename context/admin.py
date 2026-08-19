from django.contrib import admin

from .models import (
    NextActivityPlan,
    NextActivityPlanActivityTag,
    UserContextSnapshot,
    UserContextSnapshotState,
)

admin.site.register(UserContextSnapshot)
admin.site.register(UserContextSnapshotState)
admin.site.register(NextActivityPlan)
admin.site.register(NextActivityPlanActivityTag)
