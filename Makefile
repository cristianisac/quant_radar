# quant_radar — local dev shortcuts.
#
# Two modes:
#   make <target>           — runs in the local .venv (fast iteration)
#   make docker-<target>    — runs in the sandboxed container (use for any
#                             command that touches a real external API)

DOCKER ?= /Applications/Docker.app/Contents/Resources/bin/docker

.PHONY: install-ide \
        docker-build docker-check docker-lint docker-type docker-test \
        docker-shell docker-ui

# All execution of project code happens in Docker. The venv exists only
# for IDE language servers (autocomplete, jump-to-def) — never to run
# the code itself.

install-ide:
	uv venv
	uv pip install -e ".[dev]"

# Hardening flags applied to every container we run.
HARDEN = --read-only --tmpfs /tmp --tmpfs /app/data \
		--security-opt no-new-privileges --cap-drop ALL

# Lint/type/test never need the host cache — tests create tmp data via
# pytest fixtures; lint and type are static. A tmpfs at /app/data keeps
# any accidental writes ephemeral.
DOCKER_RUN_EPHEMERAL = $(DOCKER) run --rm $(HARDEN) quant-radar:dev

# Interactive sessions (shell, ui) bind-mount ./data so cached parquet
# survives between runs. Requires Docker Desktop file-sharing for ~/.
DOCKER_RUN_PERSISTENT = $(DOCKER) run --rm -it \
		--read-only --tmpfs /tmp \
		--security-opt no-new-privileges --cap-drop ALL \
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

docker-ui: docker-build
	$(DOCKER_RUN_PERSISTENT) -p 127.0.0.1:8501:8501 \
		quant-radar:dev streamlit run quant_radar/ui/app.py --server.address 0.0.0.0
