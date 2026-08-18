from django.contrib import admin

from .models import AIInsight, AIPlanRun, Notification, RecoveryPlan, RecoverySlot, WebPushSubscription

admin.site.register(AIPlanRun)
admin.site.register(RecoveryPlan)
admin.site.register(RecoverySlot)
admin.site.register(Notification)
admin.site.register(AIInsight)
admin.site.register(WebPushSubscription)
