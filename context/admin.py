from django.contrib import admin

from .models import DailyContext, DailyContextActivityTag, DailyContextState

admin.site.register(DailyContext)
admin.site.register(DailyContextActivityTag)
admin.site.register(DailyContextState)
