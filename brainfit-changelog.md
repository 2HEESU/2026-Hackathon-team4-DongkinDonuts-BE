# Brainfit 모델 / API 명세 변경 내역

팀원 모델 리뷰 + 자체 재검토 반영분. 팀원 컨펌용 정리본.

## 1. 모델 변경 (models.py)

### accounts
| 변경 | 내용 |
|---|---|
| 필드 삭제 | `User.device_code` 삭제 — `BaseModel`이 이미 제공하는 UUID PK(`id`)를 그대로 사용자 식별자로 사용 |
| 필드 삭제 | `UserSettings.camera_permission_status` 삭제 — 실제 브라우저 권한과 무관해서 DB에 둘 의미 없음 |

식별 방식: 프론트가 `X-Device-Code` 헤더로 UUID를 보내면 서버가 `User.objects.get_or_create(id=헤더값)`으로 조회/생성. 헤더 값이 UUID 형식이 아니면 400 처리 필요(view 구현 시 반영).

### common
| 변경 | 내용 |
|---|---|
| validator 추가 | `StateOption.default_difficulty`에 1~5 범위 제한 |

### context
| 변경 | 내용 |
|---|---|
| unique 제약 추가 | `DailyContext`: `(user, service_date)` unique — 하루 1개만 생성, 이후 PATCH로 수정 |
| 중복 인덱스 제거 | 위 unique 제약이 인덱스 역할도 겸하므로 기존 `Index(user, service_date)` 삭제 |
| 필드 교체 | `skipped`(단일) 삭제 → `state_skipped`, `tags_skipped`로 분리 (집중시간 건너뛰기는 `focus_time_option=SKIPPED`로 이미 표현됨) |
| FK 정책 변경 | `DailyContextActivityTag.activity_tag`, `DailyContextState.state`: `CASCADE` → `PROTECT` (카탈로그 삭제해도 과거 선택 기록 보존) |
| 서비스 로직 (모델 변경 아님) | `service_date`는 클라이언트가 안 보냄 — `User.timezone` 기준으로 서버가 "오늘"을 계산 |

### digital_state
| 변경 | 내용 |
|---|---|
| 버그 수정 | `PcUsagePattern.Meta.ordering` 제거 — 요일/시간대가 문자열이라 의도한 순서(월~일, 오전~저녁)로 정렬 안 됐음. 정렬은 serializer/view에서 처리 |
| 로직 수정(문서) | AI 단건/일괄 분기 기준을 "패턴이 하나라도 있으면"→"**오늘 요일**에 해당하는 패턴이 있으면"으로 정정 (다른 요일 데이터를 오늘에 잘못 적용하는 것 방지) |

### routines
| 변경 | 내용 |
|---|---|
| enum 추가 | `RoutineInstanceStatus`에 `CANCELED` 추가 — "시작 전 취소"와 `ABORTED`("하다가 중단")를 구분 |
| FK 정책 변경 | `ActivityType.target_state`: `SET_NULL` → `PROTECT` |
| validator 추가 | `ActivityType.min/max_difficulty`, `RoutineInstance.difficulty_level`에 1~5 범위 제한 |

### plans
| 변경 | 내용 |
|---|---|
| unique 제약 추가 | `RecoveryPlan`: `(user, plan_date)` 기준 `ACTIVE` 상태 1개만 허용 (AI 재추천 시 기존 플랜은 `REPLACED`로 전환 필요 — 서비스 로직) |
| 필드 삭제 | `RecoveryPlan.overall_reason`, `data_source_summary` 삭제 — `AIInsight`(recovery_plan만 걸고 slot/routine은 null)로 통합, 예전 `ai_reason` 정리와 동일한 논리 |
| enum 추가 | `InsightType`에 `DATA_INSIGHT` 추가 (IA 09-3 섹션과 매칭해 확정) |
| 문서 수정 | `AIPlanRun.pc_usage_patterns` 관련 문서/help_text를 "오늘 요일 패턴 기준" 분기로 정정 |

### sessions_app
| 변경 | 내용 |
|---|---|
| FK 대상 변경 | `SessionFeedback.session`(Session FK) → `recovery_slot`(RecoverySlot FK) — Wake/Shift/Reset 3개 세션마다 피드백을 묻는 문제가 있어서, 방문(슬롯) 단위 1회로 수정 |

---

## 2. 모델 변경 2차 (팀원 리뷰 반영분)

### sessions_app
| 변경 | 내용 |
|---|---|
| enum 삭제 | `SessionStatus.RESET` 삭제 — `GET /sessions/active/`가 `IN_PROGRESS`만 조회하는데 초기화 시 `RESET`으로 바뀌면 조회가 깨지는 버그. 초기화는 `status`를 `IN_PROGRESS`로 유지하고 `reset_count`만 증가 |
| unique 제약 추가 | `Session`: `(routine_instance)` 조건부(`IN_PROGRESS`) unique — 같은 루틴에 진행중 세션 중복 생성 방지 |
| unique 제약 추가 | `Session`: `(user)` 조건부(`IN_PROGRESS`) unique — 한 사용자가 동시에 여러 세션 진행 못 하게 하는 안전장치 |

### routines
| 변경 | 내용 |
|---|---|
| enum 삭제 | `RoutineInstanceStatus.ABORTED` 삭제 — 세션 중단 정책 확정: `Session`만 `ABORTED`로 기록하고 `RoutineInstance`는 `AVAILABLE`로 되돌려 재시도 가능하게 함 |
| 필드 삭제 | `RoutineInstance.stage_type` 삭제 — `ActivityType.stage_type`과 값이 어긋날 수 있는 중복 필드였음. `routine_instance.activity.stage_type`으로 대체 |

### plans
| 변경 | 내용 |
|---|---|
| 필드 삭제 | `AIPlanRun.reference_sessions`(Session M2M) 삭제 — `plans ↔ sessions_app` 순환 의존성 문제. `input_snapshot_json`에 스냅샷으로 저장 |
| 필드 삭제 | `AIPlanRun.pc_usage_patterns`(PcUsagePattern M2M) 삭제 — PC 패턴 수정 시 delete-then-create라 과거 `AIPlanRun`과의 연결이 조용히 끊어지는 문제. 마찬가지로 `input_snapshot_json`에 스냅샷 저장 |
| enum 삭제 | `SlotStatus.MISSED` 삭제 — "추천 시간이 지나도 언제든 시작 가능" 정책이라 "놓쳐서 시작 불가"를 나타내는 상태가 불필요 |

### accounts
| 변경 | 내용 |
|---|---|
| 서비스 로직 | `DeviceCodeAuthentication.authenticate()`에서 `User` 조회/생성 직후 `UserSettings.objects.get_or_create(user=user)`도 함께 호출 — `User`/`UserSettings` 1:1인데 `UserSettings`가 자동 생성 안 되던 누락 수정 |

이번 라운드에서 검토했지만 모델 변경 없이 반려하거나 보류한 것:
- `POST /accounts/users/bootstrap/` 부활 제안 → 반려. "매 요청 자동생성" 방식을 이미 구현/테스트/문서화(프론트 연동 문서 포함)까지 끝냈고, 해커톤 규모에서 단순함의 이득이 더 크다고 판단
- `context.tags_skipped` 존치 여부 → PM 확인 필요 항목으로 이동(`pm-confirm-choices.md` 6번)
- `common` 카탈로그 API 인증 예외 처리, `is_anonymous` 응답 제외 → 코드 변경 아님, view/serializer 구현 시 반영할 것

---

## 3. 모델 변경 3차 (PM 0817 기획 개정 반영)

### context
| 변경 | 내용 |
|---|---|
| unique 제약 삭제 | `DailyContext`: `(user, service_date)` 하루 1건 제약 삭제 — 알림 재진입마다 "지금 상태는 어때요?"를 다시 물어보는 흐름으로 기획이 바뀌어서, 하루에 여러 건(체크인)이 정상적으로 생길 수 있음 |

### digital_state
| 변경 | 내용 |
|---|---|
| 필드 교체 | `PcUsagePattern.time_slot`(오전/점심/오후/저녁 4구간) → `hour`(0~23시 정수) |
| 필드 교체 | `PcUsagePattern.usage_range`(1시간이하~6시간이상 5단계) → `is_used`(사용/미사용 불리언) |
| enum 삭제 | `TimeSlot`, `UsageRange` 클래스 삭제(더 이상 안 씀) |
| unique 제약 변경 | `(user, day_of_week, time_slot)` → `(user, day_of_week, hour)` |
| 근거 | PM이 보낸 0817 디자인 목업 — 요일×시간(1시간 단위) 체크박스 그리드, "전체 선택", "연속 사용 시간 분석" 기능이 이 구조를 전제로 함 |

정리하면, 하루 최대 행 수가 `context`는 무제한(체크인마다 1건), `digital_state`는 사용자당 28개(7×4)에서 168개(7×24)로 늘어남. 둘 다 해커톤 규모 데이터량에선 문제 없음.

---

## 4. 모델 변경 4차 (SessionMetricSample 제거)

| 변경 | 내용 |
|---|---|
| 모델 삭제 | `SessionMetricSample` 삭제, `POST /sessions/{id}/metric-samples/` 엔드포인트도 삭제 |
| 근거 | 실시간 자세 교정은 프론트 MediaPipe가 클라이언트에서 처리(`ActivityType.required_landmarks` 참고), 세부 측정값을 서버에 저장해 활용할 계획 없음. 세션 종료 시 요약값만 `Session.accuracy`/`metrics`에 담아 전송 |

---

## 5. API 엔드포인트 변경 (Notion 명세서)

### 제거된 엔드포인트
- `PATCH /routines/instances/{id}/start/`, `/complete/` — 세션 API가 트랜잭션으로 routine_instance 상태까지 같이 처리하기로 하면서 불필요해짐
- `GET /sessions/`(세션 목록), `GET /routines/instances/`(루틴 기록 목록) — 실제 쓰일 화면이 없어서 아래 통합 엔드포인트로 대체

### 신규 추가
- `POST /plans/recovery-slots/{id}/cancel/` — 슬롯 취소, 하위 routine_instance cascade
- `GET /plans/recovery-slots/` — 히스토리(방문 단위) 목록, 세션/루틴 목록 대체
- `GET /sessions/{id}/` — 세션 단건 조회 (기존에 빠져있던 것)
- `GET /sessions/active/` — 진행중 세션 조회(새로고침 복구용)

### 경로/메서드 변경
| 기존 | 변경 |
|---|---|
| `POST /sessions/{id}/reset/` | `PATCH /sessions/{id}/reset/` |
| `POST /plans/recovery-slots/next/` | `POST /plans/recovery-plans/today/next-slot/` |
| `POST /sessions/{id}/feedback/` | `POST /plans/recovery-slots/{id}/feedback/` |
| `PATCH /plans/recovery-slots/{id}/` (전체) | `PATCH /plans/recovery-slots/{id}/schedule/` (시간 변경 전용, status 변경 불가) |

### 공통 규칙 확정
- 인증: `X-Device-Code` 헤더 값을 `User.id`로 직접 사용
- PC 패턴 수정은 이미 생성된 오늘 계획에 소급 반영 안 됨(다음 생성부터 반영)
- 상태 변경은 프론트가 여러 API를 나눠 부르는 게 아니라 백엔드가 트랜잭션으로 묶어서 처리(세션 완료→루틴 완료→슬롯 완료 cascade 등)

### 아직 미정 (서비스 레이어 구현 시 결정) — 전부 해소됨
1. ~~부트스트랩 트리거~~ → 확정: 별도 부트스트랩 없음, `DeviceCodeAuthentication`이 매 요청 자동 생성
2. ~~"다음 추천" 트리거~~ → 확정: `POST /plans/recovery-slots/{id}/next/`(직전 슬롯 기준), 중복 생성 방지는 view 구현 시 처리
3. ~~즉시시작 제한~~ → 확정: 추천 시간 **이전** 시작은 막음(IA 원문 근거), **이후**는 언제든 가능(`MISSED` 삭제)
4. ~~세션 중단 시 routine_instance 처리~~ → 확정: `Session`만 `ABORTED`, `RoutineInstance`는 `AVAILABLE`로 되돌려 재시도 허용
5. ~~세션 초기화 시 기록 처리~~ → 확정: `metric_samples`(모델 자체 삭제됨)/`events`는 보존, RESET 이벤트 추가 기록

### 이번 라운드에 새로 생겼다가 해소된 항목
1. ~~`GET /context/daily-contexts/today/` 반환 형태~~ → 확정: 최신 1건 반환(다음 휴식 설정 화면에서 "이전 입력값 불러오기" 용도로 필요함이 PM 추가안으로 확인됨)

### 남은 미정 항목
1. `GET /plans/recovery-plans/today/` — 기존부터 확인 필요 상태로 남아있던 항목(오늘 플랜 조회, 슬롯+루틴 중첩 응답 구조)

---

Notion 명세서: https://app.notion.com/p/8df5955d7a6c4666b1b48713fbee8e61
