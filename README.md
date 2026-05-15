# quant_radar

AI-native market research dashboard. Chat-first: cards are created, modified, and saved by talking to a Claude Code session. The dashboard starts empty and grows by request.

## Status

Phase 0 — repo scaffold. See [plan/PROGRESS.md](plan/PROGRESS.md).

## Layout

```
quant_radar/        # Python package
├── core/           # Pydantic types, config
├── sources/        # data adapters (yfinance, fred, ...)
├── cache/          # on-disk cache + smart merge
├── analytics/      # indicators, channels, patterns
├── tools/          # agent-facing typed functions
├── cards/          # card spec, renderers, store
├── dashboard/      # main vs working logic
└── ui/             # Streamlit viewer
data/               # local-only, gitignored
plan/               # PROGRESS.md + plan.yaml
SKILL.md            # instructions for Claude Code sessions
```

## Local setup

```bash
make install        # uv venv + editable install with dev deps
make check          # ruff + pyright + pytest
```

## Sandboxed mode (recommended for any real API call)

External data sources can return malicious payloads. Run them inside the container:

```bash
make docker-build   # one-time
make docker-test    # run the full suite inside the sandbox
make docker-shell   # python REPL inside the sandbox
```

The container is `--read-only`, drops all Linux capabilities, has
`no-new-privileges`, and only bind-mounts `./data` for the cache.

## Working agreement

The Claude Code session that develops this project:
- Pushes only to `origin` (the `quant_radar` GitLab project).
- Pushes only feature branches (`phase-N-…`), never `main`.
- Updates `plan/PROGRESS.md` and `plan/plan.yaml` at each phase boundary.

See [SKILL.md](SKILL.md) for the full agent contract.
