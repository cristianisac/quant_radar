# quant_radar — local dev shortcuts.
#
# Two modes:
#   make <target>           — runs in the local .venv (fast iteration)
#   make docker-<target>    — runs in the sandboxed container (use for any
#                             command that touches a real external API)

DOCKER ?= /Applications/Docker.app/Contents/Resources/bin/docker

.PHONY: install lint type test check ui \
        docker-build docker-test docker-shell docker-fetch

install:
	uv venv
	uv pip install -e ".[dev]"

lint:
	.venv/bin/ruff check .

type:
	.venv/bin/pyright

test:
	.venv/bin/pytest -q

check: lint type test

ui:
	.venv/bin/streamlit run quant_radar/ui/app.py

docker-build:
	$(DOCKER) build -t quant-radar:dev .

docker-test: docker-build
	$(DOCKER) run --rm \
		--read-only --tmpfs /tmp \
		--security-opt no-new-privileges \
		--cap-drop ALL \
		-v "$(PWD)/data:/app/data" \
		quant-radar:dev

docker-shell: docker-build
	$(DOCKER) run --rm -it \
		--read-only --tmpfs /tmp \
		--security-opt no-new-privileges \
		--cap-drop ALL \
		-v "$(PWD)/data:/app/data" \
		quant-radar:dev python
