# Generated manually on 2026-08-19

import django.db.models.deletion
from django.db import migrations, models


def backfill_plan_sources(apps, schema_editor):
    RecoveryPlan = apps.get_model("plans", "RecoveryPlan")
    RecoverySlot = apps.get_model("plans", "RecoverySlot")
    AIPlanRun = apps.get_model("plans", "AIPlanRun")
    NextActivityPlan = apps.get_model("context", "NextActivityPlan")

    activity_plan_by_snapshot = {}
    for plan in NextActivityPlan.objects.order_by("created_at"):
        if plan.context_snapshot_id is not None:
            activity_plan_by_snapshot.setdefault(plan.context_snapshot_id, plan.id)

    for ai_run in AIPlanRun.objects.exclude(context_snapshot_id=None).iterator():
        next_activity_plan_id = activity_plan_by_snapshot.get(ai_run.context_snapshot_id)
        if next_activity_plan_id:
            ai_run.next_activity_plan_id = next_activity_plan_id
            ai_run.save(update_fields=["next_activity_plan"])

    for plan in RecoveryPlan.objects.all().iterator():
        context_snapshot_id = plan.daily_context_id
        next_activity_plan_id = activity_plan_by_snapshot.get(context_snapshot_id)
        input_snapshot = {}
        if plan.ai_plan_run_id:
            ai_run = AIPlanRun.objects.filter(id=plan.ai_plan_run_id).first()
            if ai_run:
                input_snapshot = ai_run.input_snapshot_json or {}

        pc_usage_patterns = input_snapshot.get("pc_usage_patterns") or []
        plan.generation_snapshot_json = {
            "service_date": str(plan.plan_date),
            "has_today_pc_usage_pattern": bool(pc_usage_patterns),
            "pc_usage_patterns": pc_usage_patterns,
            "context_snapshot": {"id": str(context_snapshot_id)} if context_snapshot_id else None,
            "next_activity_plan": {"id": str(next_activity_plan_id)} if next_activity_plan_id else None,
        }
        plan.save(update_fields=["generation_snapshot_json"])

        RecoverySlot.objects.filter(recovery_plan_id=plan.id).update(
            ai_plan_run_id=plan.ai_plan_run_id,
            context_snapshot_id=context_snapshot_id,
            next_activity_plan_id=next_activity_plan_id,
        )


def backfill_slot_notifications(apps, schema_editor):
    RecoverySlot = apps.get_model("plans", "RecoverySlot")
    Notification = apps.get_model("plans", "Notification")

    open_statuses = ["RECOMMENDED", "SCHEDULED", "CHANGED"]
    for slot in RecoverySlot.objects.filter(notification_enabled=True, status__in=open_statuses).iterator():
        scheduled_at = slot.user_changed_at or slot.scheduled_at or slot.recommended_at
        if scheduled_at is None:
            continue
        if Notification.objects.filter(recovery_slot_id=slot.id, status="PENDING").exists():
            continue
        Notification.objects.create(
            recovery_slot_id=slot.id,
            message=f"{scheduled_at:%H:%M} 회복 세션을 시작할 시간입니다.",
            scheduled_at=scheduled_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("context", "0004_user_context_snapshot_split"),
        ("plans", "0008_remove_aiplanrun_pc_usage_patterns_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="aiplanrun",
            old_name="daily_context",
            new_name="context_snapshot",
        ),
        migrations.AlterField(
            model_name="aiplanrun",
            name="context_snapshot",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ai_plan_runs",
                to="context.usercontextsnapshot",
            ),
        ),
        migrations.AddField(
            model_name="aiplanrun",
            name="next_activity_plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ai_plan_runs",
                to="context.nextactivityplan",
            ),
        ),
        migrations.AddField(
            model_name="recoveryplan",
            name="generation_snapshot_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="recoveryslot",
            name="ai_plan_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="recovery_slots",
                to="plans.aiplanrun",
            ),
        ),
        migrations.AddField(
            model_name="recoveryslot",
            name="context_snapshot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="recovery_slots",
                to="context.usercontextsnapshot",
            ),
        ),
        migrations.AddField(
            model_name="recoveryslot",
            name="next_activity_plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="recovery_slots",
                to="context.nextactivityplan",
            ),
        ),
        migrations.AddField(
            model_name="recoveryslot",
            name="notification_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(backfill_plan_sources, migrations.RunPython.noop),
        migrations.RunPython(backfill_slot_notifications, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="recoveryplan",
            name="daily_context",
        ),
    ]
