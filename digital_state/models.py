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

    분기 기준은 "패턴이 하나라도 있는지"가 아니라 "오늘 요일에 해당하는 패턴이 있는지"다.
    예: 월요일 패턴만 입력한 사용자의 화요일 계획을 만들 때 월요일 데이터를 그대로 쓰면 안 됨.
    오늘 요일 패턴이 있으면 그 날의 시간대별 데이터를 AI 추천 입력에 반영해 하루 일정을
    한 번에 생성하고, 없으면 오늘의 상황(DailyContext) 기반으로 다음 휴식 하나씩만 추천한다.
    입력 안 된 시간대는 "사용시간 0"이 아니라 "데이터 없음"으로 취급한다.
    분기 로직은 서비스 레이어(다음 단계) 담당이고, 이 모델은 입력값만 저장한다.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="pc_usage_patterns")
    day_of_week = models.CharField(max_length=3, choices=DayOfWeek.choices)
    time_slot = models.CharField(max_length=20, choices=TimeSlot.choices)
    usage_range = models.CharField(max_length=20, choices=UsageRange.choices)

    class Meta:
        # day_of_week/time_slot은 문자열이라 이 순서로 정렬해도 월~일/오전~저녁 순이 안 됨.
        # 화면 정렬은 serializer/view에서 요일·시간대 순서 딕셔너리로 처리할 것.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day_of_week", "time_slot"], name="unique_pattern_per_user_day_slot"
            )
        ]

    def __str__(self):
        return f"PcUsagePattern({self.user_id}, {self.day_of_week} {self.time_slot}, {self.usage_range})"
