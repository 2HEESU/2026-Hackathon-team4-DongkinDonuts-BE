from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from common.mixins import EnvelopeMixin

from .models import ActivityType, RoutineInstance
from .serializers import ActivityTypeSerializer, RoutineInstanceDetailSerializer

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

class RoutineInstanceDetailView(
    EnvelopeMixin,
    generics.RetrieveAPIView,
):
    """
    GET /api/v1/routines/instances/{id}/
    현재 사용자 소유의 루틴 인스턴스를 조회
    """

    serializer_class = RoutineInstanceDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return (
            RoutineInstance.objects.filter(
                recovery_slot__recovery_plan__user=self.request.user,
            )
            .select_related(
                "activity",
                "activity__target_state",
                "recovery_slot",
                "recovery_slot__recovery_plan",
            )
        )