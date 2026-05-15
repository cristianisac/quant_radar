"""Card persistence.

Two backends:
- **Main** dashboard: SQLite at ``data/cards/main.db``. Cards live until
  explicitly removed. Survives across sessions.
- **Working** dashboard: JSON at ``data/cards/working.json``. Single
  per-session scratchpad; calling ``new_working()`` overwrites it with
  an empty list.

Both stores serialize via the ``Card`` Pydantic model's JSON. The SQLite
schema is intentionally minimal: ``(id TEXT PRIMARY KEY, spec TEXT)``.
The card's ``id`` and timestamps come from the Pydantic model — we don't
duplicate them as columns to avoid drift.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

from quant_radar.cards.spec import Card, Target
from quant_radar.core.config import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id   TEXT PRIMARY KEY,
    spec TEXT NOT NULL
)
"""


def _ensure_dirs() -> None:
    paths.cards.mkdir(parents=True, exist_ok=True)


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(db_path or paths.main_db)
    conn.execute(_SCHEMA)
    return conn


# --------------------- Main (SQLite) ---------------------


def main_save(card: Card) -> Card:
    card.touch()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cards(id, spec) VALUES (?, ?)",
            (str(card.id), card.model_dump_json()),
        )
    return card


def main_remove(card_id: UUID | str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM cards WHERE id = ?", (str(card_id),))
        return cur.rowcount > 0


def main_list() -> list[Card]:
    with _connect() as conn:
        rows = conn.execute("SELECT spec FROM cards ORDER BY id").fetchall()
    return [Card.model_validate_json(spec) for (spec,) in rows]


def main_get(card_id: UUID | str) -> Card | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT spec FROM cards WHERE id = ?", (str(card_id),)
        ).fetchone()
    return Card.model_validate_json(row[0]) if row else None


# --------------------- Working (JSON) ---------------------


def _working_read() -> list[Card]:
    _ensure_dirs()
    if not paths.working_json.exists():
        return []
    raw = paths.working_json.read_text()
    if not raw.strip():
        return []
    data = json.loads(raw)
    return [Card.model_validate(c) for c in data]


def _working_write(cards: list[Card]) -> None:
    _ensure_dirs()
    payload = [json.loads(c.model_dump_json()) for c in cards]
    paths.working_json.write_text(json.dumps(payload, indent=2))


def working_save(card: Card) -> Card:
    cards = _working_read()
    card.touch()
    replaced = False
    for i, c in enumerate(cards):
        if c.id == card.id:
            cards[i] = card
            replaced = True
            break
    if not replaced:
        cards.append(card)
    _working_write(cards)
    return card


def working_remove(card_id: UUID | str) -> bool:
    cards = _working_read()
    new = [c for c in cards if str(c.id) != str(card_id)]
    if len(new) == len(cards):
        return False
    _working_write(new)
    return True


def working_list() -> list[Card]:
    return _working_read()


def working_get(card_id: UUID | str) -> Card | None:
    for c in _working_read():
        if str(c.id) == str(card_id):
            return c
    return None


def working_reset() -> None:
    """Clear the working dashboard — previous cards are intentionally lost.

    The file is left present (empty list) so the UI knows a working session
    is open. Use ``working_close`` to end the session entirely.
    """
    _working_write([])


def working_close() -> None:
    """End the working session entirely — removes ``working.json``."""
    paths.working_json.unlink(missing_ok=True)


def working_is_open() -> bool:
    return paths.working_json.exists()


# --------------------- Cross-store ---------------------


def save(card: Card, target: Target) -> Card:
    return main_save(card) if target == "main" else working_save(card)


def remove(card_id: UUID | str, target: Target) -> bool:
    return main_remove(card_id) if target == "main" else working_remove(card_id)


def list_cards(target: Target) -> list[Card]:
    return main_list() if target == "main" else working_list()


def get(card_id: UUID | str, target: Target) -> Card | None:
    return main_get(card_id) if target == "main" else working_get(card_id)


def promote_to_main(card_id: UUID | str) -> Card | None:
    """Copy a working card into main. Leaves the working copy in place."""
    card = working_get(card_id)
    if card is None:
        return None
    return main_save(card)
