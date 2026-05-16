#!/usr/bin/env bash
# Phase 14b dev launcher: FastAPI (Docker) + ttyd (host) + Vite (host).
# Streamlit-based `make app` is still the canonical launcher until Phase
# 14d cutover; this is the parallel dev environment for the React rewrite.

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
TTYD_PORT="${TTYD_PORT:-7681}"
API_PORT="${API_PORT:-8000}"
VITE_PORT="${VITE_PORT:-5173}"

DOCKER_BIN="${DOCKER_BIN:-/Applications/Docker.app/Contents/Resources/bin}"
export PATH="$DOCKER_BIN:$PATH"

if ! command -v node >/dev/null 2>&1; then
    echo "Error: node not found. Install: brew install node" >&2
    exit 1
fi
if ! command -v ttyd >/dev/null 2>&1; then
    echo "Error: ttyd not found. Install: brew install ttyd" >&2
    exit 1
fi

cleanup() {
    [[ -n "${TTYD_PID:-}"  ]] && kill "$TTYD_PID"  2>/dev/null || true
    [[ -n "${API_PID:-}"   ]] && kill "$API_PID"   2>/dev/null || true
    [[ -n "${VITE_PID:-}"  ]] && kill "$VITE_PID"  2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$REPO_DIR"

echo "──────────────────────────────────────────────────────────────"
echo "  api        → http://127.0.0.1:${API_PORT}/api/health     (FastAPI in Docker)"
echo "  ttyd       → http://127.0.0.1:${TTYD_PORT}                (Claude Code shell)"
echo "  vite (UI)  → http://127.0.0.1:${VITE_PORT}                ← open this"
echo "──────────────────────────────────────────────────────────────"
echo "  Ctrl+C in this terminal stops everything."
echo "──────────────────────────────────────────────────────────────"

# 1. FastAPI in Docker (loopback-only, sandboxed)
make docker-build >/dev/null
docker run --rm \
    --read-only --tmpfs /tmp --tmpfs /app/data \
    --security-opt no-new-privileges --cap-drop ALL \
    -v "${REPO_DIR}/data:/app/data" \
    -p 127.0.0.1:${API_PORT}:${API_PORT} \
    quant-radar:dev \
    uvicorn quant_radar.server.main:app --host 0.0.0.0 --port ${API_PORT} &
API_PID=$!

# 2. ttyd on host (claude inherits host auth / gh / git)
if command -v claude >/dev/null 2>&1; then
    CMD=(bash -c "cd '$REPO_DIR' && claude")
else
    CMD=(bash -c "cd '$REPO_DIR' && exec bash")
fi
ttyd -p "$TTYD_PORT" -i 127.0.0.1 -W "${CMD[@]}" &
TTYD_PID=$!

# 3. Vite dev server on host (HMR, proxies /api → :8000)
cd "$REPO_DIR/quant_radar-ui"
if [[ ! -d node_modules ]]; then
    echo "Installing UI dependencies (one-time)…"
    npm install --silent
fi
npm run dev &
VITE_PID=$!

wait "$VITE_PID"
