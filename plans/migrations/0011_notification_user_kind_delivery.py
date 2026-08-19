# Generated manually on 2026-08-19

import django.db.models.deletion
from django.db import migrations, models


def backfill_notification_users(apps, schema_editor):
    Notification = apps.get_model("plans", "Notification")

    for notification in Notification.objects.select_related("recovery_slot__recovery_plan").iterator():
        if notification.user_id or notification.recovery_slot_id is None:
            continue
        notification.user_id = notification.recovery_slot.recovery_plan.user_id
        notification.save(update_fields=["user"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_remove_user_is_anonymous"),
        ("plans", "0010_webpushsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="accounts.user",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("RECOVERY_SLOT", "회복 슬롯"),
                    ("REENGAGEMENT", "재진입"),
                ],
                default="RECOVERY_SLOT",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="data_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="notification",
            name="delivery_error",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="notification",
            name="recovery_slot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="plans.recoveryslot",
            ),
        ),
        migrations.RunPython(backfill_notification_users, migrations.RunPython.noop),
    ]
