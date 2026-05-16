#!/usr/bin/env bash
# Visual E2E launcher — boots FastAPI in a clean container, waits for
# /api/health, runs the Playwright suite, tears the container down.
#
# Screenshots land in data/visual_e2e/.

set -euo pipefail

DOCKER_BIN="${DOCKER_BIN:-/Applications/Docker.app/Contents/Resources/bin}"
export PATH="$DOCKER_BIN:$PATH"

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DATA_DIR="${REPO_DIR}/data"
API_PORT="${API_PORT:-8000}"
SHOTS_DIR="${DATA_DIR}/visual_e2e"

mkdir -p "$DATA_DIR" "$SHOTS_DIR"
rm -f "$SHOTS_DIR"/*.png

cleanup() {
    if [[ -n "${CID:-}" ]]; then
        docker stop "$CID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

echo "──────────────────────────────────────────────────────────────"
echo "  Visual E2E"
echo "  shots → ${SHOTS_DIR}"
echo "──────────────────────────────────────────────────────────────"

# Build the multi-stage image (includes the React bundle).
echo "Building image…"
make -C "$REPO_DIR" docker-build >/dev/null

# Start container in the background.
CID=$(docker run -d --rm \
    --read-only --tmpfs /tmp \
    --security-opt no-new-privileges --cap-drop ALL \
    -v "${DATA_DIR}:/app/data" \
    -p "127.0.0.1:${API_PORT}:${API_PORT}" \
    quant-radar:dev \
    uvicorn quant_radar.server.main:app --host 0.0.0.0 --port "${API_PORT}")
echo "container: ${CID:0:12}"

# Wait for the API to be ready.
for i in $(seq 1 30); do
    if curl -fs "http://127.0.0.1:${API_PORT}/api/health" >/dev/null 2>&1; then
        echo "API ready after ${i}s"
        break
    fi
    sleep 1
    if [[ $i -eq 30 ]]; then
        echo "API did not become ready in 30s" >&2
        docker logs "$CID" >&2 || true
        exit 1
    fi
done

# Install Playwright deps + Chromium (first run downloads ~200MB).
cd "${REPO_DIR}/quant_radar-ui"
if [[ ! -d node_modules ]]; then
    echo "Installing UI deps…"
    npm install --silent
fi
# Idempotent — Playwright skips the download if Chromium is up to date.
npx playwright install chromium 2>&1 | grep -v '^$' || true

# Run the suite. Output is line reporter; per-test logs include
# screenshot paths and pixel coverage.
npx playwright test
