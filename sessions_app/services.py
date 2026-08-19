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

def abort_session(*, user, session_id):
    with transaction.atomic():
        session = _get_session_for_update(
            user=user,
            session_id=session_id,
        )

        if session.status != SessionStatus.IN_PROGRESS:
            raise Conflict(
                "진행 중인 세션만 중단할 수 있습니다.",
            )

        routine_instance = RoutineInstance.objects.select_for_update().get(
            pk=session.routine_instance_id,
        )

        # 슬롯을 함께 잠그지만 상태는 STARTED로 유지
        RecoverySlot.objects.select_for_update().get(
            pk=session.recovery_slot_id,
        )

        ended_at = timezone.now()

        session.ended_at = ended_at
        session.duration_sec = _calculate_duration_sec(
            started_at=session.started_at,
            ended_at=ended_at,
        )
        session.status = SessionStatus.ABORTED
        session.save(
            update_fields=[
                "ended_at",
                "duration_sec",
                "status",
                "updated_at",
            ]
        )

        # 중단된 현재 루틴만 다시 수행 가능하게 변경
        routine_instance.status = RoutineInstanceStatus.AVAILABLE
        routine_instance.completed_at = None
        routine_instance.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        # 다음 RoutineInstance는 수정하지 않아 LOCKED 상태가 유지
        # RecoverySlot도 수정하지 않으므로 STARTED 상태가 유지
        return session

def complete_session(
    *,
    user,
    session_id,
    accuracy,
    metrics,
):
    with transaction.atomic():
        session = _get_session_for_update(
            user=user,
            session_id=session_id,
        )

        if session.status != SessionStatus.IN_PROGRESS:
            raise Conflict(
                "진행 중인 세션만 완료할 수 있습니다.",
            )

        routine_instance = RoutineInstance.objects.select_for_update().get(
            pk=session.routine_instance_id,
        )

        recovery_slot = RecoverySlot.objects.select_for_update().get(
            pk=session.recovery_slot_id,
        )

        ended_at = timezone.now()

        session.ended_at = ended_at
        session.duration_sec = _calculate_duration_sec(
            started_at=session.started_at,
            ended_at=ended_at,
        )
        session.accuracy = accuracy
        session.metrics = metrics
        session.status = SessionStatus.COMPLETED
        session.save(
            update_fields=[
                "ended_at",
                "duration_sec",
                "accuracy",
                "metrics",
                "status",
                "updated_at",
            ]
        )

        routine_instance.status = RoutineInstanceStatus.COMPLETED
        routine_instance.completed_at = ended_at
        routine_instance.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        next_routine_instance = (
            RoutineInstance.objects.select_for_update()
            .filter(
                recovery_slot=recovery_slot,
                sequence_no__gt=routine_instance.sequence_no,
            )
            .order_by("sequence_no")
            .first()
        )

        if next_routine_instance is not None:
            next_routine_instance.status = (
                RoutineInstanceStatus.AVAILABLE
            )
            next_routine_instance.locked_until_previous_done = False
            next_routine_instance.save(
                update_fields=[
                    "status",
                    "locked_until_previous_done",
                    "updated_at",
                ]
            )

        # 다음 루틴이 있으니 RecoverySlot은 STARTED를 유지
        else:
            recovery_slot.status = SlotStatus.COMPLETED
            recovery_slot.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        # API 응답에는 next_routine_instance를 임의로 추가하지 않음
        return session

def create_session_event(
    *,
    user,
    session_id,
    event_type,
    step_no=None,
    message="",
):
    try:
        session = Session.objects.get(
            pk=session_id,
            user=user,
        )
    except Session.DoesNotExist as exc:
        raise NotFound(
            "세션을 찾을 수 없습니다.",
        ) from exc
    
    if session.status != SessionStatus.IN_PROGRESS:
        raise Conflict(
            "진행 중인 세션에만 이벤트를 기록할 수 있습니다.",
        )
    
    return SessionEvent.objects.create(
        session=session,
        event_type=event_type,
        step_no=step_no,
        message=message,
    )

def _get_session_for_update(*, user, session_id):
    try:
        return (
            Session.objects.select_for_update()
            .select_related(
                "activity",
                "routine_instance",
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

def _calculate_duration_sec(*, started_at, ended_at):
    duration = int(
        (ended_at - started_at).total_seconds()
    )

    # 서버 시각 오차 등 음수가 저장되지 않도록 방어
    return max(0, duration)