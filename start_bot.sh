#!/bin/bash
# Ella-Bot Startup Script
# Startet Matrix-Rust-Sidecar und Python-Bot

set -euo pipefail

BOT_ROOT="/home/finklamott/demokratiebot"
SIDECAR_DIR="${BOT_ROOT}/matrix_sidecar"

cd "${BOT_ROOT}"

# Lade Umgebungsvariablen
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export MATRIX_SIDECAR_LISTEN="${MATRIX_SIDECAR_LISTEN:-127.0.0.1:8010}"
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

# Stoppe alte Instanzen
pkill -f matrix_sidecar 2>/dev/null || true
pkill -f ella-sidecar 2>/dev/null || true
screen -S sidecar -X quit 2>/dev/null || true
screen -S ella-bot -X quit 2>/dev/null || true
sleep 1

# Starte Sidecar
echo "Starting Rust Sidecar..."
screen -dmS sidecar bash -lc "cd '${SIDECAR_DIR}' && ./target/release/matrix_sidecar 2>&1 | tee sidecar.log"

# Warte bis Sidecar bereit ist
echo "Waiting for Sidecar..."
for i in {1..45}; do
  if curl -fsS "${MATRIX_SIDECAR_URL}/health" > /dev/null 2>&1; then
    echo "Sidecar ready!"
    break
  fi
  sleep 1
done

# Starte Bot
echo "Starting Ella-Bot..."
screen -dmS ella-bot bash -lc "cd '${BOT_ROOT}' && source venv/bin/activate && python src/demokratiebot_main.py 2>&1 | tee bot.log"

sleep 2
echo "Done! Running screens:"
screen -ls
