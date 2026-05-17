"""Source ABC + registry — the plug-and-play surface for data adapters.

Each adapter module declares a ``Source`` subclass with three things:

1. ``capability`` — its ``SourceCapability`` from the catalog (columns,
   intervals, auth, etc.)
2. ``supports(ref)`` — does this source handle a given ``DataRef``?
3. ``fetch(ref, refresh)`` — return the normalized DataFrame.

Subclasses register themselves at import time via ``register_source``
so ``hydrate()`` becomes a one-line registry lookup. Adding a new
source is: write the module, register the class, add a catalog entry.
No changes to the dispatch layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from quant_radar.cards.spec import DataRef
    from quant_radar.sources.catalog import SourceCapability


class Source(ABC):
    """Adapter contract. One subclass per upstream API.

    Every adapter must satisfy four capabilities so the agent has the
    same level of discovery on every source:

    - ``supports(ref)`` — gate dispatch
    - ``fetch(ref, refresh)`` — hydrate the data
    - ``search(query, limit)`` — find candidate symbols by keyword
    - ``describe(name)`` — look up the long-form metadata for one symbol

    ``search`` and ``describe`` may return empty/None when the upstream
    genuinely doesn't expose those affordances, but the *method must
    exist* — that's how the agent knows it can ask the question.
    """

    capability: "SourceCapability"

    @property
    def name(self) -> str:
        return self.capability.name

    @abstractmethod
    def supports(self, ref: "DataRef") -> bool:
        """Return True if this source can serve ``ref`` (source + kind match)."""

    @abstractmethod
    def fetch(self, ref: "DataRef", *, refresh: bool = False) -> "pd.DataFrame":
        """Fetch the frame for ``ref``. Must respect ``ref.start/end``."""

    @abstractmethod
    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        """Search for symbols matching ``query``.

        Return a list of ``{symbol, longname, ...}`` dicts. ``symbol`` is
        required, ``longname`` strongly encouraged. Other keys (exchange,
        sector, frequency, units, notes, ...) are source-specific but
        should be informative.

        Return ``[]`` when search is unsupported or upstream is
        unreachable — silent failure is fine because callers treat
        empty as "discovery unavailable".
        """

    @abstractmethod
    def describe(self, name: str) -> dict | None:
        """Return long-form metadata for one ``name`` (the symbol/series id).

        Return ``None`` if the symbol isn't recognized OR the upstream
        doesn't expose per-symbol metadata. Keys are source-specific —
        FRED returns title/notes/units, yfinance returns longName/
        sector/industry/exchange, etc.
        """


_REGISTRY: dict[str, Source] = {}


def register_source(source: Source) -> Source:
    """Idempotently register an adapter. Returns the instance for chaining."""
    _REGISTRY[source.name] = source
    return source


def get_source(name: str) -> Source | None:
    return _REGISTRY.get(name)


def all_sources() -> list[Source]:
    return list(_REGISTRY.values())
