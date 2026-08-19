#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_PATH:?DEPLOY_PATH is required}"

DEPLOY_REF="${DEPLOY_REF:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PATH="${VENV_PATH:-$DEPLOY_PATH/.venv}"
MANAGE_PY="${MANAGE_PY:-manage.py}"

cd "$DEPLOY_PATH"

echo "Deploying ref: $DEPLOY_REF"
git fetch --prune origin
git checkout "$DEPLOY_REF"
git pull --ff-only origin "$DEPLOY_REF"

if [ ! -d "$VENV_PATH" ]; then
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python "$MANAGE_PY" migrate --noinput
python "$MANAGE_PY" collectstatic --noinput

if [ -n "${RESTART_COMMAND:-}" ]; then
  eval "$RESTART_COMMAND"
elif [ -n "${SERVICE_NAME:-}" ]; then
  sudo systemctl restart "$SERVICE_NAME"
else
  echo "No restart command configured. Set SERVICE_NAME or RESTART_COMMAND."
fi

if [ -n "${HEALTHCHECK_URL:-}" ]; then
  curl --fail --show-error --silent --max-time 15 "$HEALTHCHECK_URL" > /dev/null
fi

echo "Deployment finished."
