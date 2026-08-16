from django.db import models

from common.models import BaseModel


class DayOfWeek(models.TextChoices):
    MON = "MON", "월"
    TUE = "TUE", "화"
    WED = "WED", "수"
    THU = "THU", "목"
    FRI = "FRI", "금"
    SAT = "SAT", "토"
    SUN = "SUN", "일"


class TimeSlot(models.TextChoices):
    MORNING = "MORNING", "오전"
    LUNCH = "LUNCH", "점심"
    AFTERNOON = "AFTERNOON", "오후"
    EVENING = "EVENING", "저녁"


class UsageRange(models.TextChoices):
    UNDER_1H = "UNDER_1H", "1시간 이하"
    H1_TO_2H = "H1_TO_2H", "1~2시간"
    H2_TO_4H = "H2_TO_4H", "2~4시간"
    H4_TO_6H = "H4_TO_6H", "4~6시간"
    OVER_6H = "OVER_6H", "6시간 이상"


# 요일×시간대별 PC 사용 패턴 입력값(있으면 AI가 하루치 일괄 추천의 근거로 사용)
class PcUsagePattern(BaseModel):
    """
    Digital State 수정본. 스크린타임/스마트폰 캡처+OCR, 기기·환경 선택 관련 내용은
    전부 삭제하고 이 모델 하나로 대체함 (요일 × 시간대별 PC 사용 패턴).

    이 데이터가 있으면 AI가 하루치 휴식 일정을 한 번에 생성(RecoverySlot 여러 개),
    없으면 오늘의 상황(DailyContext) 기반으로 다음 휴식 하나씩 추천하는 방식으로 분기한다.
    분기 로직은 서비스 레이어(다음 단계) 담당이고, 이 모델은 입력값만 저장한다.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="pc_usage_patterns")
    day_of_week = models.CharField(max_length=3, choices=DayOfWeek.choices)
    time_slot = models.CharField(max_length=20, choices=TimeSlot.choices)
    usage_range = models.CharField(max_length=20, choices=UsageRange.choices)

    class Meta:
        ordering = ["user", "day_of_week", "time_slot"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day_of_week", "time_slot"], name="unique_pattern_per_user_day_slot"
            )
        ]

    def __str__(self):
        return f"PcUsagePattern({self.user_id}, {self.day_of_week} {self.time_slot}, {self.usage_range})"
