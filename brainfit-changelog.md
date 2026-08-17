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

## 2. API 엔드포인트 변경 (Notion 명세서)

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

### 아직 미정 (서비스 레이어 구현 시 결정)
1. 부트스트랩 트리거 — 프론트 명시 호출 vs 미들웨어 자동 생성
2. "다음 추천" 트리거 — 프론트 명시 호출 vs 이전 슬롯 완료 시 서버 자동 생성
3. 세션 시작 시 예약 시간 이전 즉시시작을 서버가 막을지
4. 세션 중단(ABORTED) 시 routine_instance를 ABORTED로 같이 마크할지, AVAILABLE로 되돌려 재시도 허용할지
5. 세션 초기화 시 기존 metric_samples/events 삭제 여부, routine_instance 동기화 여부

---

Notion 명세서: https://app.notion.com/p/8df5955d7a6c4666b1b48713fbee8e61
