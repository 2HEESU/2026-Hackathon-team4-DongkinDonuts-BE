import uuid

from django.db import models


# UUID 기반 PK를 제공하는 추상 베이스
class UUIDModel(models.Model):
    """ERD의 CHAR(36) id에 대응. 팀 ERD가 전부 UUID PK라 이걸 표준으로 맞춘다."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


# 생성/수정 시각을 자동 기록하는 추상 베이스
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# 도메인 모델들이 공통으로 상속하는 베이스(UUID PK + 생성/수정 시각)
class BaseModel(UUIDModel, TimeStampedModel):
    """UUID PK + 생성/수정시각. 대부분의 도메인 모델이 이걸 상속한다."""

    class Meta:
        abstract = True


# 온보딩 활동 태그(#코딩, #과제 등) 사전 정의 목록
class ActivityTag(models.Model):
    """
    ERD: activity_tags
    온보딩에서 고르는 활동 태그(#코딩, #과제 등) 사전 정의 목록. 다른 앱(context)에서
    참조하므로 순환 참조를 피하려고 공용 앱(common)에 둔다.
    """

    code = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=50)
    category = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# '현재 상태' 선택지(눈이 피곤해요 등) 사전 정의 목록
class StateOption(models.Model):
    """
    ERD: state_options
    '현재 상태' 고정 어휘(눈이 피곤해요 등). context(오늘의 상태 선택)와
    routines(활동별 target_state) 양쪽에서 참조하므로 공용 앱에 둔다.
    """

    code = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=50)
    default_difficulty = models.PositiveSmallIntegerField(default=1)
    routine_direction = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.label
