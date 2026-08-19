from django.db import migrations


ACTIVITY_TYPES = [
    {
        "code": "WAKE_BREATH",
        "stage_type": "BRAIN_WAKE",
        "target_state_id": None,
        "name": "짧은 호흡 깨우기",
        "purpose": "가볍게 호흡을 정리하며 감각과 주의를 깨웁니다.",
        "required_landmarks": [],
        "min_difficulty": 1,
        "max_difficulty": 3,
        "default_duration_sec": 60,
    },
    {
        "code": "WAKE_EYE_MOVE",
        "stage_type": "BRAIN_WAKE",
        "target_state_id": None,
        "name": "시선 움직이기",
        "purpose": "눈과 시선을 부드럽게 움직이며 본격 활동 전 감각을 깨웁니다.",
        "required_landmarks": ["LEFT_EYE", "RIGHT_EYE"],
        "min_difficulty": 1,
        "max_difficulty": 3,
        "default_duration_sec": 60,
    },
    {
        "code": "SHIFT_EYE_RELAX",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "EYE_TIRED",
        "name": "눈 피로 풀기",
        "purpose": "화면 사용으로 긴장된 눈과 시선을 쉬게 합니다.",
        "required_landmarks": ["LEFT_EYE", "RIGHT_EYE"],
        "min_difficulty": 1,
        "max_difficulty": 4,
        "default_duration_sec": 90,
    },
    {
        "code": "SHIFT_FOCUS_SWITCH",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "LOW_FOCUS",
        "name": "집중 전환하기",
        "purpose": "흩어진 주의를 짧게 전환하고 다시 모읍니다.",
        "required_landmarks": [],
        "min_difficulty": 1,
        "max_difficulty": 4,
        "default_duration_sec": 90,
    },
    {
        "code": "SHIFT_BODY_STRETCH",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "BODY_STIFF",
        "name": "상체 긴장 풀기",
        "purpose": "굳은 목, 어깨, 상체를 가볍게 움직입니다.",
        "required_landmarks": ["LEFT_SHOULDER", "RIGHT_SHOULDER"],
        "min_difficulty": 1,
        "max_difficulty": 5,
        "default_duration_sec": 120,
    },
    {
        "code": "SHIFT_DROWSY_WAKE",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "SLEEPY",
        "name": "졸림 깨우기",
        "purpose": "처진 각성을 무리 없이 끌어올립니다.",
        "required_landmarks": [],
        "min_difficulty": 1,
        "max_difficulty": 4,
        "default_duration_sec": 90,
    },
    {
        "code": "SHIFT_LIGHT_REFRESH",
        "stage_type": "BRAIN_SHIFT",
        "target_state_id": "OKAY",
        "name": "가벼운 컨디션 유지",
        "purpose": "좋은 컨디션을 유지하도록 짧게 리프레시합니다.",
        "required_landmarks": [],
        "min_difficulty": 1,
        "max_difficulty": 3,
        "default_duration_sec": 60,
    },
    {
        "code": "RESET_BREATH",
        "stage_type": "BRAIN_RESET",
        "target_state_id": None,
        "name": "호흡 마무리",
        "purpose": "호흡과 간단한 이완으로 세션을 마무리합니다.",
        "required_landmarks": [],
        "min_difficulty": 1,
        "max_difficulty": 3,
        "default_duration_sec": 60,
    },
]


def seed_activity_types(apps, schema_editor):
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


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0003_seed_brainfit_state_options"),
        ("routines", "0003_remove_routineinstance_stage_type_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_activity_types, migrations.RunPython.noop),
    ]
