# Generated manually on 2026-08-19

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_remove_user_is_anonymous"),
        ("plans", "0009_context_snapshot_sources"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebPushSubscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="web_push_subscriptions",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]
