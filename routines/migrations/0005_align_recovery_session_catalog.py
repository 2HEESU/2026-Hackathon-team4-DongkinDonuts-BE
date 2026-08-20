from django.db import migrations


ACTIVITY_TYPES = [
    {
        "code": "WAKE_HAND_ROUTINE",
        "stage_type": "BRAIN_WAKE",
        "target_state_id": None,
        "name": "손 감각 깨우기",
        "purpose": "손을 활용한 가벼운 움직임으로 회복 세션을 시작합니다.",
        "required_landmarks": ["LEFT_HAND", "RIGHT_HAND"],
        "min_difficulty": 1,
        "max_difficulty": 3,
        "default_duration_sec": 60,
    },
    {
        "code": "SHIFT_EYE_TRACKING",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "EYE_TIRED",
        "name": "시선 타겟 따라가기",
        "purpose": "시선을 움직이며 화면으로 굳은 눈 주변 긴장을 낮춥니다.",
        "required_landmarks": ["LEFT_EYE", "RIGHT_EYE"],
        "min_difficulty": 1,
        "max_difficulty": 4,
        "default_duration_sec": 90,
    },
    {
        "code": "SHIFT_SHOULDER_PMR",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "BODY_STIFF",
        "name": "어깨 점진 이완",
        "purpose": "어깨에 힘을 주고 풀며 목과 어깨의 긴장을 낮춥니다.",
        "required_landmarks": ["LEFT_SHOULDER", "RIGHT_SHOULDER"],
        "min_difficulty": 1,
        "max_difficulty": 5,
        "default_duration_sec": 120,
    },
]


def align_recovery_session_catalog(apps, schema_editor):
    ActivityType = apps.get_model("routines", "ActivityType")

    for activity in ACTIVITY_TYPES:
        ActivityType.objects.update_or_create(
            code=activity["code"],
            defaults={
                "stage_type": activity["stage_type"],
                "target_state_id": activity["target_state_id"],
                "name": activity["name"],
                "purpose": activity["purpose"],
                "required_landmarks": activity["required_landmarks"],
                "min_difficulty": activity["min_difficulty"],
                "max_difficulty": activity["max_difficulty"],
                "default_duration_sec": activity["default_duration_sec"],
                "is_active": True,
            },
        )

    ActivityType.objects.filter(
        code__in=["WAKE_BREATH", "WAKE_EYE_MOVE"],
        stage_type="BRAIN_WAKE",
    ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("routines", "0004_seed_brainfit_activity_types"),
    ]

    operations = [
        migrations.RunPython(align_recovery_session_catalog, migrations.RunPython.noop),
    ]
