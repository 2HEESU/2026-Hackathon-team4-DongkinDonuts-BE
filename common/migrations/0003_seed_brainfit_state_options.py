from django.db import migrations


STATE_OPTIONS = [
    {
        "code": "EYE_TIRED",
        "label": "눈이 피곤해요",
        "default_difficulty": 2,
        "routine_direction": "눈과 시선 피로를 낮추는 가벼운 움직임",
    },
    {
        "code": "LOW_FOCUS",
        "label": "집중이 안 돼요",
        "default_difficulty": 2,
        "routine_direction": "주의를 전환하고 다시 모으는 짧은 리프레시",
    },
    {
        "code": "BODY_STIFF",
        "label": "몸이 굳었어요",
        "default_difficulty": 3,
        "routine_direction": "목, 어깨, 상체 긴장을 풀어주는 움직임",
    },
    {
        "code": "SLEEPY",
        "label": "졸려요",
        "default_difficulty": 2,
        "routine_direction": "처진 각성을 부드럽게 끌어올리는 활동",
    },
    {
        "code": "OKAY",
        "label": "괜찮아요",
        "default_difficulty": 1,
        "routine_direction": "현재 컨디션을 유지하는 가벼운 정리 활동",
    },
]


def seed_state_options(apps, schema_editor):
    StateOption = apps.get_model("common", "StateOption")
    for option in STATE_OPTIONS:
        StateOption.objects.update_or_create(
            code=option["code"],
            defaults={
                "label": option["label"],
                "default_difficulty": option["default_difficulty"],
                "routine_direction": option["routine_direction"],
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0002_alter_stateoption_default_difficulty"),
    ]

    operations = [
        migrations.RunPython(seed_state_options, migrations.RunPython.noop),
    ]
