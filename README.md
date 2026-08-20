동킨 도너츠의 Brainfit 백엔드 레포지토리입니다!

# 팀원 소개
<table>
  <tbody>
    <tr>
      <td align="center"><a href="https://github.com/hp4323000"><img src="" width="100px;" alt=""/><br /><sub><b>기획/디자인 : 정서현</b></sub></a><br /></td>
      <td align="center"><a href="https://github.com/rhtjdco"><img src="" width="100px;" alt=""/><br /><sub><b>FE : 고성채</b></sub></a><br /></td>
      <td align="center"><a href="https://github.com/Yunseo2727"><img src="" width="100px;" alt=""/><br /><sub><b>FE : 노윤서</b></sub></a><br /></td>
      <td align="center"><a href="https://github.com/2HEESU"><img src="" width="100px;" alt=""/><br /><sub><b>BE : 이희수</b></sub></a><br /></td>
      <td align="center"><a href="https://github.com/hw4nx02"><img src="" width="100px;" alt=""/><br /><sub><b>BE : 이창환</b></sub></a><br /></td>
    <td align="center"><a href="https://github.com/junhnno"><img src="" width="100px;" alt=""/><br /><sub><b>BE : 황준호</b></sub></a><br /></td>
     <tr/>
  </tbody>
</table>

# 프로젝트 소개

## Tech

### 라이브러리

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
