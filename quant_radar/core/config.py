"""Filesystem paths and runtime config.

The repo root is detected from this file's location so paths are stable
regardless of where the package is imported from.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    data: Path
    cache: Path
    cards: Path
    main_db: Path
    working_json: Path

    def ensure(self) -> None:
        for p in (self.data, self.cache, self.cards):
            p.mkdir(parents=True, exist_ok=True)


def _build_paths(root: Path) -> Paths:
    data = root / "data"
    cache = data / "cache"
    cards = data / "cards"
    return Paths(
        repo_root=root,
        data=data,
        cache=cache,
        cards=cards,
        main_db=cards / "main.db",
        working_json=cards / "working.json",
    )


paths = _build_paths(_REPO_ROOT)
