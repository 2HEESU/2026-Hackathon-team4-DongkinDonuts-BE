from django.contrib import admin

from .models import Session, SessionEvent, SessionFeedback

admin.site.register(Session)
admin.site.register(SessionEvent)
admin.site.register(SessionFeedback)
