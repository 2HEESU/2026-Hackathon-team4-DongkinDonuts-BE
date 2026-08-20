from django.urls import path

from .views import (
    NotificationClickView,
    NotificationListView,
    RecoveryPlanTodayAIGenerateView,
    RecoveryPlanResetNextActivityView,
    RecoveryPlanTodayNextSlotView,
    RecoveryPlanTodayView,
    RecoverySlotCancelView,
    RecoverySlotCancelBeforeView,
    RecoverySlotConsumeSnapshotView,
    RecoverySlotListView,
    RecoverySlotDetailView,
    RecoverySlotFeedbackView,
    RecoverySlotHistoryView,
    RecoverySlotNextResetTimeView,
    RecoverySlotNextView,
    RecoverySlotNotificationView,
    RecoverySlotResetNextActivityView,
    RecoverySlotScheduleView,
    RecoverySlotTodayListView,
    WebPushVapidPublicKeyView,
    WebPushSubscriptionDeleteView,
    WebPushSubscriptionListCreateView,
)

app_name = "plans"
urlpatterns = [
    path("recovery-plans/today/", RecoveryPlanTodayView.as_view(), name="recovery-plan-today"),
    path(
        "recovery-plans/today/ai-generate/",
        RecoveryPlanTodayAIGenerateView.as_view(),
        name="recovery-plan-today-ai-generate",
    ),
    path(
        "recovery-plans/today/next-slot/",
        RecoveryPlanTodayNextSlotView.as_view(),
        name="recovery-plan-today-next-slot",
    ),
    path(
        "recovery-plans/today/reset-next-activity/",
        RecoveryPlanResetNextActivityView.as_view(),
        name="recovery-plan-reset-next-activity",
    ),
    path("recovery-slots/", RecoverySlotListView.as_view(), name="recovery-slot-list"),
    path("recovery-slots/today/", RecoverySlotTodayListView.as_view(), name="recovery-slot-today-list"),
    path(
        "recovery-slots/cancel-before/",
        RecoverySlotCancelBeforeView.as_view(),
        name="recovery-slot-cancel-before",
    ),
    path(
        "recovery-slots/consume-nearest-snapshot/",
        RecoverySlotConsumeSnapshotView.as_view(),
        name="recovery-slot-consume-nearest-snapshot",
    ),
    path("recovery-slots/next/", RecoverySlotNextView.as_view(), name="recovery-slot-next"),
    path(
        "recovery-slots/next-reset-time/",
        RecoverySlotNextResetTimeView.as_view(),
        name="recovery-slot-next-reset-time",
    ),
    path("recovery-slots/history/", RecoverySlotHistoryView.as_view(), name="recovery-slot-history"),
    path(
        "recovery-slots/<uuid:pk>/reset-next-activity/",
        RecoverySlotResetNextActivityView.as_view(),
        name="recovery-slot-reset-next-activity",
    ),
    path("recovery-slots/<uuid:pk>/", RecoverySlotDetailView.as_view(), name="recovery-slot-detail"),
    path("recovery-slots/<uuid:pk>/feedback/", RecoverySlotFeedbackView.as_view(), name="recovery-slot-feedback"),
    path("recovery-slots/<uuid:pk>/schedule/", RecoverySlotScheduleView.as_view(), name="recovery-slot-schedule"),
    path(
        "recovery-slots/<uuid:pk>/notification/",
        RecoverySlotNotificationView.as_view(),
        name="recovery-slot-notification",
    ),
    path("recovery-slots/<uuid:pk>/cancel/", RecoverySlotCancelView.as_view(), name="recovery-slot-cancel"),
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<uuid:pk>/click/", NotificationClickView.as_view(), name="notification-click"),
    path(
        "notification-subscriptions/",
        WebPushSubscriptionListCreateView.as_view(),
        name="notification-subscription-list-create",
    ),
    path(
        "notification-subscriptions/vapid-public-key/",
        WebPushVapidPublicKeyView.as_view(),
        name="notification-subscription-vapid-public-key",
    ),
    path(
        "notification-subscriptions/<uuid:pk>/",
        WebPushSubscriptionDeleteView.as_view(),
        name="notification-subscription-delete",
    ),
]
