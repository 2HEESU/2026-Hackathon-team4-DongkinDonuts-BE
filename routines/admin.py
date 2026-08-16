from django.contrib import admin

from .models import ActivityType, RoutineInstance

admin.site.register(ActivityType)
admin.site.register(RoutineInstance)
