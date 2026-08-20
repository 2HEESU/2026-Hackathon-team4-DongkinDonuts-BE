from django.db import migrations, models


def backfill_notification_basis(apps, schema_editor):
    RecoverySlot = apps.get_model("plans", "RecoverySlot")

    for slot in RecoverySlot.objects.select_related("recovery_plan").iterator():
        snapshot = slot.recovery_plan.generation_snapshot_json or {}
        if snapshot.get("has_today_pc_usage_pattern"):
            slot.notification_basis = "FREQUENCY"
            slot.save(update_fields=["notification_basis"])


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0011_notification_user_kind_delivery"),
    ]

    operations = [
        migrations.AddField(
            model_name="recoveryslot",
            name="notification_basis",
            field=models.CharField(
                choices=[
                    ("SNAPSHOT", "스냅샷 기반"),
                    ("FREQUENCY", "빈도 기반"),
                ],
                default="SNAPSHOT",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_notification_basis, migrations.RunPython.noop),
    ]
