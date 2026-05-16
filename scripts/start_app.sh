#!/usr/bin/env bash
# Launch both the Streamlit viewer (Docker) and a ttyd terminal (host)
# that runs Claude Code in the project directory. Loopback-only on both
# ports — never exposed to the LAN.
#
# Ctrl+C in this terminal stops both.

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
TTYD_PORT="${TTYD_PORT:-7681}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"

if ! command -v ttyd >/dev/null 2>&1; then
    echo "Error: ttyd is not installed. Install with: brew install ttyd" >&2
    exit 1
fi
if ! command -v claude >/dev/null 2>&1; then
    echo "Warning: 'claude' CLI not found on PATH. The terminal will still" >&2
    echo "open but Claude Code won't auto-start. Run 'claude' manually inside." >&2
fi

cleanup() {
    if [[ -n "${TTYD_PID:-}" ]]; then
        kill "$TTYD_PID" 2>/dev/null || true
        wait "$TTYD_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "──────────────────────────────────────────────────────────────"
echo "  ttyd       → http://127.0.0.1:${TTYD_PORT}  (Claude Code shell)"
echo "  streamlit  → http://127.0.0.1:${STREAMLIT_PORT}  (dashboard + embedded terminal)"
echo "──────────────────────────────────────────────────────────────"
echo "  Open http://127.0.0.1:${STREAMLIT_PORT} in your browser."
echo "  Toggle 'Show terminal' in the sidebar to embed the shell."
echo "  Ctrl+C in this terminal stops everything."
echo "──────────────────────────────────────────────────────────────"

# Start ttyd on the host (so claude has access to host auth, gh, etc.).
# -W = writable. Default startup command: bash in the project dir, then
# auto-launch claude if it's on PATH (with -p "read SKILL.md ...").
if command -v claude >/dev/null 2>&1; then
    CMD=(bash -c "cd '$REPO_DIR' && claude")
else
    CMD=(bash -c "cd '$REPO_DIR' && exec bash")
fi

ttyd -p "$TTYD_PORT" -i 127.0.0.1 -W "${CMD[@]}" &
TTYD_PID=$!

# Give ttyd a moment to bind before opening the browser-facing UI.
sleep 1

# Block on docker-ui; trap cleans up ttyd when this exits.
make docker-ui
