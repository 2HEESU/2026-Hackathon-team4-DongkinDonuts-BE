from django.contrib import admin

from .models import Session, SessionEvent, SessionFeedback, SessionMetricSample

admin.site.register(Session)
admin.site.register(SessionMetricSample)
admin.site.register(SessionEvent)
admin.site.register(SessionFeedback)
