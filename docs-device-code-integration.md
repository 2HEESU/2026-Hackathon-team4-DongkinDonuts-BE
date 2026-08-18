# 사용자 식별 방식 (X-Device-Code)

Brainfit은 로그인 기능이 없습니다. 대신 프론트가 발급한 UUID를 매 요청마다 헤더로 보내면,
서버가 그 값을 그대로 사용자 식별자로 사용합니다.

## 프론트가 해야 할 일

1. **앱 첫 접속 시**, `localStorage`에 저장된 값이 있는지 확인한다.
2. **없으면** `crypto.randomUUID()`로 새 UUID를 만들어 `localStorage`에 저장한다.
   **있으면** 새로 만들지 않고 기존 값을 그대로 사용한다. (재방문 시 같은 사용자로 인식되려면 필수)
3. **이후 모든 API 요청**에 아래 헤더를 포함해서 보낸다.

```
X-Device-Code: 550e8400-e29b-41d4-a716-446655440000
```

### 예시 코드 (프론트 참고용)

```js
function getDeviceCode() {
  let code = localStorage.getItem("device_code");
  if (!code) {
    code = crypto.randomUUID();
    localStorage.setItem("device_code", code);
  }
  return code;
}

// API 요청 시
fetch("/api/v1/context/daily-contexts/today/", {
  headers: {
    "X-Device-Code": getDeviceCode(),
  },
});
```

## 서버가 하는 일

- `X-Device-Code` 헤더 값을 받아서, 그 UUID로 사용자를 조회한다.
- 없는 값이면 새 사용자를 자동 생성한다.
- 있는 값이면 기존 사용자로 인식한다.
- **별도의 "회원가입" API 호출은 필요 없다** — 이 헤더만 정상적으로 보내면 서버가 알아서 처리한다.

## 주의사항

| 상황 | 서버 반응 |
|---|---|
| 헤더 자체가 없음 | 비로그인 상태로 처리(막힌 요청이 아니라면 그냥 진행) |
| 헤더는 있는데 UUID 형식이 아님 | `401 Unauthorized` |
| 정상 UUID (처음 보는 값) | 새 사용자 생성 |
| 정상 UUID (기존 값) | 기존 사용자로 인식 |

**한계**: 이 방식은 "같은 사람"이 아니라 "같은 값을 들고 온 브라우저"를 인식하는 것이다.
사용자가 `localStorage`를 지우거나 다른 브라우저/기기로 접속하면 새 사용자로 인식된다.

## 참고: 모든 API 공통 응답 형식

성공:
```json
{ "success": true, "data": { ... }, "message": null }
```

실패:
```json
{ "success": false, "error": { "code": "...", "message": "...", "details": null } }
```
