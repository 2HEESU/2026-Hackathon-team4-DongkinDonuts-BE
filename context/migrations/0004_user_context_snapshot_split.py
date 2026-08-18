# Generated manually on 2026-08-19

import django.db.models.deletion
import uuid
from django.db import migrations, models


def copy_next_activity_plans(apps, schema_editor):
    UserContextSnapshot = apps.get_model("context", "UserContextSnapshot")
    DailyContextActivityTag = apps.get_model("context", "DailyContextActivityTag")
    NextActivityPlan = apps.get_model("context", "NextActivityPlan")
    NextActivityPlanActivityTag = apps.get_model("context", "NextActivityPlanActivityTag")

    for snapshot in UserContextSnapshot.objects.all().iterator():
        activity_plan = NextActivityPlan.objects.create(
            user_id=snapshot.user_id,
            context_snapshot_id=snapshot.id,
            service_date=snapshot.service_date,
            expected_activity_minutes=snapshot.expected_focus_minutes,
        )
        NextActivityPlanActivityTag.objects.bulk_create(
            NextActivityPlanActivityTag(
                next_activity_plan=activity_plan,
                activity_tag_id=link.activity_tag_id,
            )
            for link in DailyContextActivityTag.objects.filter(daily_context_id=snapshot.id)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_remove_user_is_anonymous"),
        ("common", "0002_alter_stateoption_default_difficulty"),
        ("context", "0003_remove_dailycontext_unique_user_service_date"),
        ("digital_state", "0006_remove_pcusagepattern_unique_pattern_per_user_day_slot_and_more"),
        ("plans", "0008_remove_aiplanrun_pc_usage_patterns_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="DailyContext",
            new_name="UserContextSnapshot",
        ),
        migrations.RenameModel(
            old_name="DailyContextState",
            new_name="UserContextSnapshotState",
        ),
        migrations.RemoveConstraint(
            model_name="usercontextsnapshotstate",
            name="unique_daily_context_state",
        ),
        migrations.RenameField(
            model_name="usercontextsnapshotstate",
            old_name="daily_context",
            new_name="context_snapshot",
        ),
        migrations.AlterField(
            model_name="usercontextsnapshot",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="context_snapshots",
                to="accounts.user",
            ),
        ),
        migrations.CreateModel(
            name="NextActivityPlan",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("service_date", models.DateField(db_index=True)),
                ("expected_activity_minutes", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "context_snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="next_activity_plans",
                        to="context.usercontextsnapshot",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="next_activity_plans",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-service_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="NextActivityPlanActivityTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "activity_tag",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="common.activitytag"),
                ),
                (
                    "next_activity_plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_tag_links",
                        to="context.nextactivityplan",
                    ),
                ),
            ],
        ),
        migrations.RunPython(copy_next_activity_plans, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="DailyContextActivityTag",
        ),
        migrations.RemoveField(
            model_name="usercontextsnapshot",
            name="expected_focus_minutes",
        ),
        migrations.RemoveField(
            model_name="usercontextsnapshot",
            name="focus_time_option",
        ),
        migrations.RemoveField(
            model_name="usercontextsnapshot",
            name="state_skipped",
        ),
        migrations.RemoveField(
            model_name="usercontextsnapshot",
            name="tags_skipped",
        ),
        migrations.AddField(
            model_name="usercontextsnapshot",
            name="state_options",
            field=models.ManyToManyField(
                blank=True,
                related_name="context_snapshots",
                through="context.UserContextSnapshotState",
                to="common.stateoption",
            ),
        ),
        migrations.AddField(
            model_name="nextactivityplan",
            name="activity_tags",
            field=models.ManyToManyField(
                blank=True,
                related_name="next_activity_plans",
                through="context.NextActivityPlanActivityTag",
                to="common.activitytag",
            ),
        ),
        migrations.AddConstraint(
            model_name="usercontextsnapshotstate",
            constraint=models.UniqueConstraint(
                fields=("context_snapshot", "state"),
                name="unique_context_snapshot_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="nextactivityplanactivitytag",
            constraint=models.UniqueConstraint(
                fields=("next_activity_plan", "activity_tag"),
                name="unique_next_activity_plan_tag",
            ),
        ),
    ]
