<div align="center">

# 🧠 Brainfit — Backend

**동킨 도너츠**의 Brainfit 백엔드 레포지토리입니다!

멋쟁이사자처럼 동국대학교 중앙해커톤 4팀

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white"/>
<img src="https://img.shields.io/badge/Django%20REST%20Framework-A30000?style=for-the-badge&logo=django&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white"/>
<img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white"/>
<img src="https://img.shields.io/badge/Web%20Push-FF6F00?style=for-the-badge&logo=googlechrome&logoColor=white"/>
<br/>
<img src="https://img.shields.io/badge/Gunicorn-499848?style=for-the-badge&logo=gunicorn&logoColor=white"/>
<img src="https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white"/>
<img src="https://img.shields.io/badge/Gabia%20Cloud-FF6600?style=for-the-badge"/>
<img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white"/>

</div>

# 👥 팀원 소개

<table>
  <tbody>
    <tr>
      <td align="center" width="260">
        <img src="https://github.com/hp4323000.png" width="100" height="100" alt="정서현"/><br/>
        <sub><b>📌 정서현 (PM)</b></sub><br/>
        Preliminary · Design<br/>
        📧 hp4323000@naver.com<br/>
        🔗 <a href="https://github.com/hp4323000">GitHub</a><br/>
        <i>"행복하자!!"</i>
      </td>
      <td align="center" width="260">
        <img src="https://github.com/rhtjdco.png" width="100" height="100" alt="고성채"/><br/>
        <sub><b>📌 고성채 (Front-end)</b></sub><br/>
        Front-end<br/>
        📧 gsc2926@naver.com<br/>
        🔗 <a href="https://github.com/rhtjdco">GitHub</a><br/>
        <i>"제가 키우는 아이들"</i>
      </td>
    </tr>
    <tr>
      <td align="center" width="260">
        <img src="https://github.com/Yunseo2727.png" width="100" height="100" alt="노윤서"/><br/>
        <sub><b>📌 노윤서 (Front-end)</b></sub><br/>
        Front-end<br/>
        📧 yunseo272727@naver.com<br/>
        🔗 <a href="https://github.com/Yunseo2727">GitHub</a><br/>
        <i>"토닥토닥토닥 화이팅 토닥토닥"</i>
      </td>
      <td align="center" width="260">
        <img src="https://github.com/hw4nx02.png" width="100" height="100" alt="이창환"/><br/>
        <sub><b>📌 이창환 (Back-end)</b></sub><br/>
        Back-end<br/>
        📧 2002ckdgnks99@gmail.com<br/>
        🔗 <a href="https://github.com/hw4nx02">GitHub</a><br/>
        <i>"잘 부탁드립니다~~~~"</i>
      </td>
    </tr>
    <tr>
      <td align="center" width="260">
        <img src="https://github.com/2HEESU.png" width="100" height="100" alt="이희수"/><br/>
        <sub><b>📌 이희수 (Back-end)</b></sub><br/>
        Back-end<br/>
        📧 sunf05121@gmail.com<br/>
        🔗 <a href="https://github.com/2HEESU">GitHub</a><br/>
        <i>"힘을 내어봅시다"</i>
      </td>
      <td align="center" width="260">
        <img src="https://github.com/junhnno.png" width="100" height="100" alt="황준호"/><br/>
        <sub><b>📌 황준호 (Back-end)</b></sub><br/>
        Back-end<br/>
        📧 withardor03@gmail.com<br/>
        🔗 <a href="https://github.com/junhnno">GitHub</a><br/>
        <i>"너굴쓰"</i>
      </td>
    </tr>
  </tbody>
</table>

# 프로젝트 소개

**Brainfit**은 노트북/PC 앞에서 오래 앉아있는 사용자가 "지친 순간"을 놓치지 않고
짧은 회복 루틴으로 다시 깨어날 수 있게 돕는 AI 웰니스 서비스입니다. 이 레포는
그 백엔드로, 로그인 없이 기기별 UUID(`X-Device-Code`)로 사용자를 식별하는
Django REST API입니다. 상태 기반 회복 타이머부터 PC 사용 패턴을 학습한 AI 자율
알림 스케줄링, 웹 푸시 발송, 손/얼굴 트래킹 세션 기록까지 담당합니다.

## 주요 기능

### 🧘 상태 선택 → 회복 루틴
사용자가 지금 상태("눈이 피로해요", "졸려요" 등)와 다음 활동 예정 시간을
입력하면, 상태별 회복 타이머 정책(20~90분)에 따라 일정한 간격으로 반복 알림을
예약합니다. 알림을 누르면 손/얼굴 트래킹 기반 3단계 루틴(Brain Wake → Brain
Shift → Brain Reset)으로 바로 진입합니다.

### 📊 My Digital State — PC 사용 패턴 기반 AI 자율 판단
요일별 PC 사용 시간대를 입력하면, OpenAI 모델이 사용자의 과거 세션 이력·PC
사용 밀집도를 분석해 알림 개수와 발송 시각을 스스로 판단합니다
(`plans/ai_planner.py`). LLM이 설정되지 않았거나 실패하면 서버 정책 엔진
(`plans/services.py`)이 자동으로 대체합니다:

- 최근 세션 기록이 3회 이상 몰린 시간대를 우선 배치(이력 기반, 간격 불균일)
- 이력이 부족한 PC 사용 블록은 상태별 인터벌로 균일 반복
- PC 사용 블록이 여러 개면 라운드로빈으로 하루 알림 상한(12개)을 공평하게 배분

이 흐름은 상태 선택 모달 흐름과 완전히 독립적으로 동작합니다 — 한쪽을 다시
생성해도 다른 쪽이 예약해둔 알림은 건드리지 않습니다.

### 🔔 웹 푸시 알림
`pywebpush` 기반 실제 Web Push 구독/발송을 지원합니다(VAPID). 예약된 알림은
주기적으로 발송 대기열을 확인해 발송하고, 만료/실패한 구독은 자동
비활성화합니다.

### 🖐️ 손/얼굴 트래킹 회복 세션
루틴 활동 카탈로그(`routines`)를 기준으로 난이도별 세션을 구성하고, 완료/피드백
이력을 기록해 "Your History"에서 조회할 수 있습니다.

### 🎬 데모 모드
현장 시연/촬영 시 서버 환경변수 `DEMO_MODE=true`만 켜면(레포 코드 변경 없이)
회복 인터벌이 분 단위 대신 초 단위(10~30초)로 동작합니다. 기본값은 항상
`False`라 제출 코드/평가에는 영향이 없습니다.

## Tech

### 앱 구성

| 앱 | 역할 |
| --- | --- |
| `accounts` | 기기 코드 기반 사용자 식별, 설정 |
| `common` | 상태/활동 태그 등 공용 카탈로그 |
| `context` | 오늘의 상태 스냅샷, 다음 활동 계획 |
| `digital_state` | PC 사용 패턴 입력/분석 |
| `plans` | 회복 계획·슬롯·알림·AI 플래너 (핵심 도메인) |
| `routines` | 회복 루틴 활동 카탈로그, 진행 인스턴스 |
| `sessions_app` | 실제 트래킹 세션 기록/피드백 |

### 인증
로그인 없이 `X-Device-Code` 헤더(브라우저가 생성한 UUID)로 사용자를
식별합니다. 서버는 이 값을 그대로 `accounts.User.id`로 사용해 최초 요청 시
자동 생성(get_or_create)합니다.

### 라이브러리

- **Django 6 / Django REST Framework** — API 서버
- **django-environ** — 환경변수 기반 설정
- **django-cors-headers** — 프론트엔드 CORS 허용
- **pywebpush** — Web Push 알림 발송(VAPID)
- **OpenAI API**(`urllib`로 직접 호출, 별도 SDK 미사용) — My Digital State AI
  자율 판단
- **SQLite** — 개발/운영 DB

## 컨벤션
1. 작업 전 반드시 pull 받고 진행

2. `requirements.txt` 변경사항 있을 시
   - 소통 채널 활용하여 공지
   - `README.md`의 `사용 라이브러리` 항목 수정
   - 아래 명령어 수행

     ```bash
     pip install -r requirements.txt
     ```

3. Git 컨벤션은 [위키](https://github.com/LikeLion-at-DGU/) 참고

## 가비아 클라우드 자동 배포

GitHub Actions가 `main`, `develop`, `release/**` 브랜치에 push될 때 Django 체크와 테스트를 먼저 실행하고, 통과하면 가비아 클라우드 서버에 SSH로 접속해 배포합니다. 수동 배포가 필요하면 GitHub Actions의 `Deploy to Gabia Cloud` 워크플로우에서 `Run workflow`로 실행할 수 있습니다.

### 서버 최초 준비

서버에 SSH로 접속한 뒤 아래 항목을 준비합니다.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

서버의 배포 경로에 저장소를 clone합니다.

```bash
git clone https://github.com/LikeLion-at-DGU/2026-Hackathon-team4-DongkinDonuts-BE.git /home/ubuntu/brainfit-be
cd /home/ubuntu/brainfit-be
```

운영 환경 변수는 서버의 `/home/ubuntu/brainfit-be/.env`에 둡니다. GitHub Actions는 이 파일을 덮어쓰지 않습니다.

### GitHub Secrets

저장소의 `Settings` > `Secrets and variables` > `Actions`에 아래 Secrets를 등록합니다.

| Secret | 필수 | 설명 |
| --- | --- | --- |
| `GABIA_HOST` | 예 | 가비아 클라우드 서버 공인 IP 또는 도메인 |
| `GABIA_USER` | 예 | SSH 접속 사용자명 |
| `GABIA_SSH_KEY` | 예 | 서버 접속용 private key 전체 내용 |
| `GABIA_DEPLOY_PATH` | 예 | 서버의 저장소 경로. 예: `/home/ubuntu/brainfit-be` |
| `GABIA_SSH_PORT` | 아니오 | SSH 포트. 기본값: `22` |
| `GABIA_SERVICE_NAME` | 아니오 | 재시작할 systemd 서비스명. 예: `brainfit` |
| `GABIA_RESTART_COMMAND` | 아니오 | systemd가 아닐 때 사용할 재시작 명령. `GABIA_SERVICE_NAME`보다 우선합니다. |
| `GABIA_KNOWN_HOSTS` | 아니오 | 고정 known_hosts 값. 없으면 Actions가 `ssh-keyscan`으로 등록합니다. |
| `GABIA_HEALTHCHECK_URL` | 아니오 | 배포 후 확인할 URL |
| `GABIA_PYTHON_BIN` | 아니오 | 서버 Python 실행 파일. 기본값: `python3` |
| `GABIA_VENV_PATH` | 아니오 | 서버 가상환경 경로. 기본값: `$GABIA_DEPLOY_PATH/.venv` |

### 배포 흐름

서버에서는 `scripts/deploy.sh`가 아래 순서로 실행됩니다.

```bash
git fetch --prune origin
git checkout "$DEPLOY_REF"
git pull --ff-only origin "$DEPLOY_REF"
python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
sudo systemctl restart "$GABIA_SERVICE_NAME"
```

배포 대상 브랜치를 바꾸려면 `.github/workflows/deploy.yml`의 `on.push.branches` 목록을 수정합니다.
