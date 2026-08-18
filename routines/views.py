from rest_framework import generics
from rest_framework.permissions import AllowAny

from common.mixins import EnvelopeMixin

from .models import ActivityType
from .serializers import ActivityTypeSerializer

# Create your views here.
class ActivityTypeListView(
    EnvelopeMixin,
    generics.ListAPIView,
):
    """
    GET /api/v1/routines/activity-types/
    활성화된 Brainfit 활동 카탈로그를 조회
    """

    queryset = ActivityType.objects.filter(
        is_active=True
    ).order_by("code")

    serializer_class = ActivityTypeSerializer

    authentication_classes = []
    permission_classes = [AllowAny]