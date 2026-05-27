# quant_radar — local dev shortcuts.
#
# All execution of project code happens in Docker. The local .venv (if
# present via `make install-ide`) exists only for IDE language servers
# — never to run the code itself.

# Docker Desktop's binaries live here on macOS. We prepend this to PATH
# **only when `make` runs** so `docker build` can find its credential
# helper (`docker-credential-desktop`). This does NOT leak into the
# user's shell — it's scoped to make's sub-processes only.
DOCKER_BIN := /Applications/Docker.app/Contents/Resources/bin
DOCKER ?= $(DOCKER_BIN)/docker
export PATH := $(DOCKER_BIN):$(PATH)

.PHONY: install-ide \
        docker-build docker-check docker-lint docker-type docker-test \
        docker-shell docker-api app dev \
        ui-install ui-build ui-typecheck visual-e2e tools-doc

install-ide:
	uv venv
	uv pip install -e ".[dev]"

# Hardening flags applied to every ephemeral container run.
#
# `--read-only` was dropped when we added OpenBB Platform: OpenBB's import
# runs a `_PackageBuilder.auto_build()` that writes generated Python and a
# .build.lock file into its own install dir. Pre-building at image-build
# time doesn't help because the lock write happens on every import.
# Skipping auto-build via OPENBB_AUTO_BUILD=False leaves the high-level
# `obb.equity.*` API empty — unusable. Dropping --read-only is the
# pragmatic trade-off; we still get cap-drop + no-new-privileges + tmpfs
# for known mutable paths, which covers the realistic threat model
# (untrusted upstream API responses, malicious pip package payloads).
HARDEN = --tmpfs /tmp --tmpfs /app/data \
		--tmpfs /home/radar/.openbb_platform:exec,uid=1000,gid=1000 \
		--tmpfs /home/radar/.cache:exec,uid=1000,gid=1000 \
		--security-opt no-new-privileges --cap-drop ALL

# Lint/type/test never need the host cache.
DOCKER_RUN_EPHEMERAL = $(DOCKER) run --rm $(HARDEN) quant-radar:dev

# --env-file is silently ignored if .env is absent, so the developer
# never has to set FRED_API_KEY for the rest of the stack to start.
ENV_FILE_ARG = $(if $(wildcard .env),--env-file .env,)

# Interactive sessions bind-mount ./data so cached parquet survives.
# (See HARDEN comment for why --read-only is no longer here.)
DOCKER_RUN_PERSISTENT = $(DOCKER) run --rm -it \
		--tmpfs /tmp \
		--tmpfs /home/radar/.openbb_platform:exec,uid=1000,gid=1000 \
		--tmpfs /home/radar/.cache:exec,uid=1000,gid=1000 \
		--security-opt no-new-privileges --cap-drop ALL \
		$(ENV_FILE_ARG) \
		-v "$(PWD)/data:/app/data"

docker-build:
	$(DOCKER) build -t quant-radar:dev .

docker-lint: docker-build
	$(DOCKER_RUN_EPHEMERAL) ruff check --no-cache .

docker-type: docker-build
	$(DOCKER_RUN_EPHEMERAL) pyright

docker-test: docker-build
	$(DOCKER_RUN_EPHEMERAL) pytest -q -p no:cacheprovider

docker-check: docker-lint docker-type docker-test

docker-shell: docker-build
	$(DOCKER_RUN_PERSISTENT) quant-radar:dev python

# FastAPI alone (no ttyd). Useful for curl / Postman testing.
docker-api: docker-build
	$(DOCKER_RUN_PERSISTENT) \
		-p 127.0.0.1:8000:8000 \
		quant-radar:dev \
		uvicorn quant_radar.server.main:app --host 0.0.0.0 --port 8000

# Full app — FastAPI (serves API + React bundle) + ttyd (host) for the
# embedded Claude Code terminal. Open http://127.0.0.1:8000.
# Requires `ttyd` on host (brew install ttyd) and `claude` on PATH.
app:
	@bash scripts/start_app.sh

# Dev launcher with HMR — FastAPI (Docker) + ttyd (host) + Vite (host).
# Open http://127.0.0.1:5173 once started.
dev:
	@bash scripts/start_dev.sh

# UI build helpers — Node on host for HMR speed.
ui-install:
	cd quant_radar-ui && npm install

ui-build:
	cd quant_radar-ui && npm run build

ui-typecheck:
	cd quant_radar-ui && npm run typecheck

# Comprehensive visual E2E — boots FastAPI in a clean container, drives
# a headless Chromium via Playwright, screenshots every card type and
# UI interaction. Each chart card is checked for non-blank pixel
# coverage so silent render failures fail loudly. First run downloads
# Chromium (~200MB, host-only — no Docker bloat).
visual-e2e:
	@bash scripts/visual_e2e.sh

# Regenerate TOOLS.md from the live registry (CATALOG + tools.__all__ +
# kind_relationships + kind_coverage). Run after any change to those
# registries. The committed TOOLS.md is the single source of truth for
# "what does this codebase expose to the agent".
tools-doc:
	$(DOCKER) run --rm $(HARDEN) $(ENV_FILE_ARG) \
		-v "$$(pwd)/scripts:/app/scripts:ro" \
		quant-radar:dev \
		python scripts/generate_tools_doc.py > TOOLS.md
	@echo "regenerated TOOLS.md ($$(wc -l < TOOLS.md) lines)"
