from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from accounts.models import User
from plans.models import (
    Notification,
    NotificationStatus,
    RecoverySlot,
    SlotStatus,
)
from routines.models import (
    RoutineInstance,
    RoutineInstanceStatus,
)

from .exceptions import Conflict
from .models import Session, SessionEvent, SessionStatus


def start_session(
    *,
    user,
    routine_instance_id,
    camera_permission_status,
):
    try:
        with transaction.atomic():
            # 동일 사용자의 동시 세션 시작 요청을 직렬화
            User.objects.select_for_update().get(pk=user.pk)

            try:
                routine_instance = (
                    RoutineInstance.objects.select_for_update()
                    .select_related(
                        "activity",
                        "recovery_slot",
                        "recovery_slot__recovery_plan",
                    )
                    .get(
                        pk=routine_instance_id,
                        recovery_slot__recovery_plan__user=user,
                    )
                )
            except RoutineInstance.DoesNotExist as exc:
                raise NotFound(
                    "루틴 인스턴스를 찾을 수 없습니다.",
                ) from exc

            recovery_slot = RecoverySlot.objects.select_for_update().get(
                pk=routine_instance.recovery_slot_id,
            )

            if recovery_slot.status in [
                SlotStatus.CANCELED,
                SlotStatus.COMPLETED,
            ]:
                raise Conflict(
                    "취소되거나 완료된 회복 슬롯은 시작할 수 없습니다.",
                )

            # 이미 진행 중인 세션이 있는지 먼저 확인
            if Session.objects.filter(
                routine_instance=routine_instance,
                status=SessionStatus.IN_PROGRESS,
            ).exists():
                raise Conflict(
                    "해당 루틴에 이미 진행 중인 세션이 있습니다.",
                )

            if Session.objects.filter(
                user=user,
                status=SessionStatus.IN_PROGRESS,
            ).exists():
                raise Conflict(
                    "이미 진행 중인 세션이 있습니다.",
                )

            if routine_instance.status != RoutineInstanceStatus.AVAILABLE:
                raise Conflict(
                    "현재 진행 가능한 루틴이 아닙니다.",
                )

            previous_incomplete_exists = (
                RoutineInstance.objects.select_for_update()
                .filter(
                    recovery_slot=recovery_slot,
                    sequence_no__lt=routine_instance.sequence_no,
                )
                .exclude(status=RoutineInstanceStatus.COMPLETED)
                .exists()
            )

            if previous_incomplete_exists:
                raise Conflict(
                    "이전 루틴을 완료한 후 시작할 수 있습니다.",
                )

            now = timezone.now()

            # 예약 시간 전 시작을 포함하여 슬롯을 즉시 시작 상태로 변경
            recovery_slot.status = SlotStatus.STARTED
            recovery_slot.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            # 기존 예약 알림은 삭제하지 않고 취소 상태로 변경
            Notification.objects.filter(
                recovery_slot=recovery_slot,
                status=NotificationStatus.PENDING,
            ).update(
                status=NotificationStatus.CANCELED,
                updated_at=now,
            )

            routine_instance.status = RoutineInstanceStatus.IN_PROGRESS
            routine_instance.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            return Session.objects.create(
                user=user,
                recovery_slot=recovery_slot,
                routine_instance=routine_instance,
                activity=routine_instance.activity,
                started_at=now,
                status=SessionStatus.IN_PROGRESS,
                camera_permission_status=camera_permission_status,
            )

    except IntegrityError as exc:
        # 서비스 레이어 검증과 DB 요청 사이에 동시 요청이 들어와 UniqueConstraint가 발생한 경우에도 409로 통일
        raise Conflict(
            "이미 진행 중인 세션이 존재합니다.",
        ) from exc


def reset_session(*, user, session_id):
    with transaction.atomic():
        try:
            session = (
                Session.objects.select_for_update()
                .select_related(
                    "routine_instance",
                    "activity",
                    "recovery_slot",
                )
                .get(
                    pk=session_id,
                    user=user,
                )
            )
        except Session.DoesNotExist as exc:
            raise NotFound(
                "세션을 찾을 수 없습니다.",
            ) from exc

        if session.status != SessionStatus.IN_PROGRESS:
            raise Conflict(
                "진행 중인 세션만 초기화할 수 있습니다.",
            )

        now = timezone.now()

        session.started_at = now
        session.ended_at = None
        session.duration_sec = None
        session.accuracy = None
        session.streak_count = 0
        session.metrics = None
        session.reset_count += 1
        session.status = SessionStatus.IN_PROGRESS
        session.save()

        routine_instance = session.routine_instance
        routine_instance.status = RoutineInstanceStatus.IN_PROGRESS
        routine_instance.completed_at = None
        routine_instance.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        SessionEvent.objects.create(
            session=session,
            event_type="RESET",
            message="세션이 초기화되었습니다.",
        )

        return session