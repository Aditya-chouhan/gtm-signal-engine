"""Orchestration: turn per-source Signal lists into one ranked, composite
entity table. This module has no network calls in it -- it's pure
aggregation, which is what makes it unit-testable offline (see
tests/test_engine.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .entities import ENTITIES
from .scoring import Signal, aggregate_entity_score, score_signal


@dataclass
class EntityResult:
    ticker: str
    name: str
    composite_score: float
    signal_count: int
    by_source: dict  # source -> count, for the "was this corroborated across sources" question


def build_entity_table(signals: list[Signal], half_life_days: float,
                        now: datetime | None = None) -> list[EntityResult]:
    by_ticker: dict[str, list[Signal]] = {}
    for sig in signals:
        by_ticker.setdefault(sig.ticker, []).append(sig)

    name_by_ticker = {e.ticker: e.name for e in ENTITIES}
    results = []
    for ticker, entity_signals in by_ticker.items():
        scores = [score_signal(s, half_life_days, now) for s in entity_signals]
        composite = aggregate_entity_score(scores)
        by_source: dict[str, int] = {}
        for s in entity_signals:
            by_source[s.source] = by_source.get(s.source, 0) + 1
        results.append(EntityResult(
            ticker=ticker,
            name=name_by_ticker.get(ticker, ticker),
            composite_score=composite,
            signal_count=len(entity_signals),
            by_source=by_source,
        ))

    # Entities with zero signals still get a row at score 0 -- absence of
    # signal is itself information (this entity is quiet right now), and
    # dropping them silently would make the output look like a filtered
    # top-N rather than a full scored universe.
    seen = {r.ticker for r in results}
    for e in ENTITIES:
        if e.ticker not in seen:
            results.append(EntityResult(e.ticker, e.name, 0.0, 0, {}))

    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results
