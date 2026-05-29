#!/usr/bin/env bash
# Production-style launcher: FastAPI (Docker, serves API + built React
# bundle) + ttyd (host, runs Claude Code). One browser tab — both the
# dashboard and the embedded terminal live at http://127.0.0.1:8000.
#
# Ctrl+C in this terminal stops both.

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
TTYD_PORT="${TTYD_PORT:-7681}"
API_PORT="${API_PORT:-8000}"

DOCKER_BIN="${DOCKER_BIN:-/Applications/Docker.app/Contents/Resources/bin}"
export PATH="$DOCKER_BIN:$PATH"

if ! command -v ttyd >/dev/null 2>&1; then
    echo "Error: ttyd not found. Install: brew install ttyd" >&2
    exit 1
fi

cleanup() {
    [[ -n "${TTYD_PID:-}" ]] && kill "$TTYD_PID" 2>/dev/null || true
    [[ -n "${API_PID:-}"  ]] && kill "$API_PID"  2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$REPO_DIR"

echo "──────────────────────────────────────────────────────────────"
echo "  app   → http://127.0.0.1:${API_PORT}             (dashboard + API)"
echo "  ttyd  → http://127.0.0.1:${TTYD_PORT}             (Claude Code shell)"
echo "──────────────────────────────────────────────────────────────"
echo "  Open http://127.0.0.1:${API_PORT} in your browser."
echo "  Toggle 'Show terminal' in the sidebar to embed the shell."
echo "  Ctrl+C in this terminal stops everything."
echo "──────────────────────────────────────────────────────────────"

# Build the image (includes the React bundle baked in via the Node stage).
make docker-build >/dev/null

# --env-file passes FRED_API_KEY (and any future secret) into the API
# container without ever showing it on the command line. Skipped if no
# .env exists.
ENV_FILE_ARG=()
if [[ -f "${REPO_DIR}/.env" ]]; then
    ENV_FILE_ARG=(--env-file "${REPO_DIR}/.env")
fi

# 1. FastAPI in Docker (serves both /api/* and the React bundle at /).
#
# Harden flags mirror the Makefile HARDEN target. --read-only was dropped
# when OpenBB landed because OpenBB's import writes generated Python +
# a .build.lock on every fresh module load (see CLAUDE.md decision #7).
# Instead we tmpfs every writable path OpenBB and its extensions touch:
# /home/radar/.openbb_platform (auto-build lock + settings) and
# /home/radar/.cache (HF tokenizers + misc). /app/data is host-mounted
# (not tmpfs) so the parquet cache survives container restarts in this
# production launcher.
docker run --rm \
    --tmpfs /tmp \
    --tmpfs /home/radar/.openbb_platform:exec,uid=1000,gid=1000 \
    --tmpfs /home/radar/.cache:exec,uid=1000,gid=1000 \
    --security-opt no-new-privileges --cap-drop ALL \
    "${ENV_FILE_ARG[@]}" \
    -v "${REPO_DIR}/data:/app/data" \
    -p 127.0.0.1:${API_PORT}:${API_PORT} \
    quant-radar:dev \
    uvicorn quant_radar.server.main:app --host 0.0.0.0 --port ${API_PORT} &
API_PID=$!

# 2. ttyd on host (so Claude Code inherits host auth / gh / git).
#
# Launch claude with a warmup query as the first turn so the SKILL.md +
# TOOLS.md preload happens during the few seconds the user spends
# reading the dashboard — not on their first real prompt. Shifts the
# ~2s read overhead out of the user's interactive path.
WARMUP="Read SKILL.md and TOOLS.md fully, then reply 'ready' (one word)."
if command -v claude >/dev/null 2>&1; then
    CMD=(bash -c "cd '$REPO_DIR' && claude '$WARMUP'")
else
    CMD=(bash -c "cd '$REPO_DIR' && exec bash")
fi
ttyd -p "$TTYD_PORT" -i 127.0.0.1 -W "${CMD[@]}" &
TTYD_PID=$!

# 3. Wait until the API is actually serving, then auto-open the browser.
# The Docker image pulls OpenBB which takes 5-10s to import on first run;
# poll /api/health rather than guessing a fixed sleep.
APP_URL="http://127.0.0.1:${API_PORT}"
echo "  Waiting for API at ${APP_URL}/api/health ..."
for _ in $(seq 1 60); do
    if curl -sf "${APP_URL}/api/health" >/dev/null 2>&1; then
        echo "  → ready. Opening browser."
        open "${APP_URL}" 2>/dev/null || true
        break
    fi
    sleep 1
done

wait "$API_PID"
