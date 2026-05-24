#!/usr/bin/env bash
# Launch the OpenBB MCP server with API keys sourced from the repo's
# .env file. Keys never appear in shell history or in `claude mcp add`
# arguments — they're loaded into the MCP subprocess env at startup
# only, where OpenBB's provider machinery reads them automatically.
#
# Registered via:
#   claude mcp add openbb -s user -- /path/to/scripts/openbb-mcp.sh
#
# Honors FMP_API_KEY, TIINGO_API_KEY, POLYGON_API_KEY, FRED_API_KEY,
# FINNHUB_API_KEY — anything OpenBB's providers consume. Missing keys
# degrade gracefully (the relevant provider returns auth errors when
# called; others still work).

set -euo pipefail

# Repo root resolved from this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source .env if present. `set -a` auto-exports every variable defined
# in the file so children (the MCP server below) inherit them.
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

# Hand off to the actual MCP server. exec replaces this shell so
# signal handling (SIGINT from Claude Code) reaches the Python process
# directly without an extra layer.
exec uv tool run --from openbb-mcp-server openbb-mcp --transport stdio
