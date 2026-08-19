from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mixins import EnvelopeMixin

from .models import Session, SessionStatus
from .serializers import (
    SessionCompleteSerializer,
    SessionEventCreateSerializer,
    SessionEventSerializer,
    SessionSerializer,
    SessionStartSerializer,
)
from .services import (
    abort_session,
    complete_session,
    create_session_event,
    reset_session,
    start_session,
)

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

class SessionAbortView(EnvelopeMixin, APIView):
    """
    PATCH /api/v1/sessions/{id}/abort/
    현재 진행 중인 세션을 중단
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        session = abort_session(
            user=request.user,
            session_id=id,
        )

        return Response(
            SessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )

class SessionCompleteView(EnvelopeMixin, APIView):
    """
    PATCH /api/v1/sessions/{id}/complete/
    현재 진행 중인 세션을 완료
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        request_serializer = SessionCompleteSerializer(
            data=request.data,
        )
        request_serializer.is_valid(
            raise_exception=True,
        )

        session = complete_session(
            user=request.user,
            session_id=id,
            accuracy=request_serializer.validated_data[
                "accuracy"
            ],
            metrics=request_serializer.validated_data.get(
                "metrics"
            ),
        )

        return Response(
            SessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )

class SessionEventCreateView(EnvelopeMixin, APIView):
    """
    POST /api/v1/sessions/{id}/events/
    세션 진행 중 이벤트 기록 (카메라 끊김 등)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        request_serializer = SessionEventCreateSerializer(
            data=request.data,
        )
        request_serializer.is_valid(raise_exception=True)

        event = create_session_event(
            user=request.user,
            session_id=id,
            event_type=request_serializer.validated_data["event_type"],
            step_no=request_serializer.validated_data.get("step_no"),
            message=request_serializer.validated_data.get("message", ""),
        )

        return Response(
            SessionEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )