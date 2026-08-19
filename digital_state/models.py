from django.core.validators import MaxValueValidator, MinValueValidator
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


# 요일×시(0~23) 단위 PC 사용 여부(있으면 AI가 하루치 일괄 추천의 근거로 사용)
class PcUsagePattern(BaseModel):
    """
    Digital State 수정본. 스크린타임/스마트폰 캡처+OCR, 기기·환경 선택 관련 내용은
    전부 삭제하고 이 모델 하나로 대체함 (요일 × 시간대별 PC 사용 패턴).

    0817 PM 기획 개정: 시간대를 오전/점심/오후/저녁(4개 구간) 대신 0~23시 1시간 단위로,
    사용량을 1시간이하~6시간이상(5단계 카테고리) 대신 사용/미사용 체크박스(O,X)로 변경.
    "전체 선택"(한 시간대를 월~일 전체에 체크), "연속 사용 시간 분석"(체크된 시간대가
    이어지는 구간 파악) 같은 기능이 이 그리드 구조를 전제로 함(디자인 목업으로 확인함).

    분기 기준은 "패턴이 하나라도 있는지"가 아니라 "오늘 요일에 해당하는 패턴이 있는지"다.
    예: 월요일 패턴만 입력한 사용자의 화요일 계획을 만들 때 월요일 데이터를 그대로 쓰면 안 됨.
    오늘 요일 패턴이 있으면 그 날의 시간대별 데이터를 AI 추천 입력에 반영해 하루 일정을
    한 번에 생성하고, 없으면 상태 스냅샷과 이후 활동 계획 기반으로 다음 휴식 하나씩만 추천한다.
    입력 안 된 시(hour)는 "미사용(is_used=False)"이 아니라 "데이터 없음(row 자체가 없음)"으로
    취급한다 — is_used=False는 사용자가 명시적으로 "안 썼다"고 체크한 것과 구분해야 함.
    분기 로직은 서비스 레이어(다음 단계) 담당이고, 이 모델은 입력값만 저장한다.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="pc_usage_patterns")
    day_of_week = models.CharField(max_length=3, choices=DayOfWeek.choices)
    hour = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(23)])
    is_used = models.BooleanField(default=False)

    class Meta:
        # day_of_week는 문자열이라 이 순서로 정렬해도 월~일 순이 안 됨.
        # 화면 정렬은 serializer/view에서 요일 순서 딕셔너리로 처리할 것.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day_of_week", "hour"], name="unique_pattern_per_user_day_hour"
            )
        ]

    def __str__(self):
        used = "사용" if self.is_used else "미사용"
        return f"PcUsagePattern({self.user_id}, {self.day_of_week} {self.hour}시, {used})"
