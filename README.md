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

## Running anything (Docker only)

All project code runs inside the sandboxed container:

```bash
make docker-build   # one-time (or after dep changes)
make docker-check   # ruff + pyright + pytest in the sandbox  ← the commit gate
make docker-test    # just the tests
make docker-shell   # python REPL in the sandbox
make docker-ui      # Streamlit UI (later phases)
```

The container is `--read-only`, drops all Linux capabilities, has
`no-new-privileges`, and only bind-mounts `./data` for the cache. Malicious
responses from external APIs cannot persist outside that directory.

## IDE setup (optional, no code execution)

For autocomplete and jump-to-def in your editor:

```bash
make install-ide    # creates .venv for language servers only
```

This venv is **not** used to run the code — only for static IDE features.

## Working agreement

The Claude Code session that develops this project:
- Pushes only to `origin` (the `quant_radar` GitLab project).
- Pushes only feature branches (`phase-N-…`), never `main`.
- Updates `plan/PROGRESS.md` and `plan/plan.yaml` at each phase boundary.

See [SKILL.md](SKILL.md) for the full agent contract.
