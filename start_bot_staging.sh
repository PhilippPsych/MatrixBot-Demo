#!/bin/bash
# Ella-Bot STAGING Startup Script
# Startet Matrix-Rust-Sidecar und Python-Bot fuer Staging-Umgebung
# Port 8011 (Prod: 8010) | Screen-Sessions: sidecar-staging, ella-staging

set -euo pipefail

BOT_ROOT="/home/mxbotlab-admin/mx/bots/demokratiebot-staging"
SIDECAR_DIR="${BOT_ROOT}/matrix_sidecar"

cd "${BOT_ROOT}"

# Lade Staging-Umgebungsvariablen
if [[ -f .env.staging ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.staging
  set +a
else
  echo "Error: .env.staging fehlt in ${BOT_ROOT}"
  echo "Kopiere .env.staging.example und befuelle es mit Staging-Credentials."
  exit 1
fi

export MATRIX_SIDECAR_LISTEN="${MATRIX_SIDECAR_LISTEN:-127.0.0.1:8011}"
export MATRIX_SIDECAR_URL="${MATRIX_SIDECAR_URL:-http://${MATRIX_SIDECAR_LISTEN}}"
export MATRIX_SIDECAR_STORE="${MATRIX_SIDECAR_STORE:-${SIDECAR_DIR}/store}"
export RUST_LOG="${RUST_LOG:-info,matrix_sdk=warn}"

if [[ -z "${MATRIX_PASSWORD:-}" && -n "${MATRIX_ACCESS_TOKEN:-}" && -z "${MATRIX_DEVICE_ID:-}" ]]; then
  echo "Error: MATRIX_DEVICE_ID fehlt fuer Access-Token-Login. Setze MATRIX_PASSWORD oder MATRIX_DEVICE_ID."
  exit 1
fi

if [[ ! -x "${SIDECAR_DIR}/target/release/matrix_sidecar" ]]; then
  echo "Error: ${SIDECAR_DIR}/target/release/matrix_sidecar fehlt. Bitte zuerst bauen:"
  echo "  cd ${SIDECAR_DIR} && source ~/.cargo/env && cargo build --release --locked --offline"
  exit 1
fi

# Stoppe nur Staging-Instanzen (NICHT Produktion!)
screen -S sidecar-staging -X quit 2>/dev/null || true
screen -S ella-staging -X quit 2>/dev/null || true
sleep 1

# Starte Sidecar (Staging)
echo "Starting Staging Sidecar on ${MATRIX_SIDECAR_LISTEN}..."
screen -dmS sidecar-staging bash -lc "cd '${SIDECAR_DIR}' && ./target/release/matrix_sidecar 2>&1 | tee sidecar-staging.log"

# Warte bis Sidecar bereit ist
echo "Waiting for Staging Sidecar..."
for i in {1..45}; do
  if curl -fsS "${MATRIX_SIDECAR_URL}/health" > /dev/null 2>&1; then
    echo "Staging Sidecar ready!"
    break
  fi
  sleep 1
done

# Starte Bot (Staging)
echo "Starting Ella-Bot (Staging)..."
screen -dmS ella-staging bash -lc "cd '${BOT_ROOT}' && source venv/bin/activate && python src/demokratiebot_main.py 2>&1 | tee bot-staging.log"

sleep 2
echo "Done! Running screens:"
screen -ls
