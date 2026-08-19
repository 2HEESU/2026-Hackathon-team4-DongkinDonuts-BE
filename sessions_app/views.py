from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mixins import EnvelopeMixin

from .models import Session, SessionStatus
from .serializers import (
    SessionSerializer,
    SessionStartSerializer,
)
from .services import reset_session, start_session

# Create your views here.
class ActiveSessionView(EnvelopeMixin, APIView):
    """
    GET /api/v1/sessions/active/
    현재 사용자의 진행 중 세션을 조회
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        session = (
            Session.objects.filter(
                user=request.user,
                status=SessionStatus.IN_PROGRESS,
            )
            .select_related(
                "activity",
                "activity__target_state",
                "routine_instance",
                "recovery_slot",
            )
            .prefetch_related("events")
            .first()
        )

        if session is None:
            return Response(None, status=status.HTTP_200_OK)

        return Response(
            SessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )

class SessionDetailView(
    EnvelopeMixin,
    generics.RetrieveAPIView,
):
    """
    GET /api/v1/sessions/{id}/
    현재 사용자 소유의 세션을 조회
    """

    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return (
            Session.objects.filter(user=self.request.user)
            .select_related(
                "activity",
                "activity__target_state",
                "routine_instance",
                "recovery_slot",
            )
            .prefetch_related("events")
        )

class SessionStartView(EnvelopeMixin, APIView):
    """
    POST /api/v1/sessions/
    루틴 인스턴스를 기반으로 세션을 시작
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_serializer = SessionStartSerializer(
            data=request.data,
        )
        request_serializer.is_valid(raise_exception=True)

        session = start_session(
            user=request.user,
            routine_instance_id=request_serializer.validated_data[
                "routine_instance_id"
            ],
            camera_permission_status=request_serializer.validated_data[
                "camera_permission_status"
            ],
        )

        return Response(
            SessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )

class SessionResetView(EnvelopeMixin, APIView):
    """
    PATCH /api/v1/sessions/{id}/reset/
    진행 중인 세션을 STEP 1 상태로 초기화
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        session = reset_session(
            user=request.user,
            session_id=id,
        )

        return Response(
            SessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )