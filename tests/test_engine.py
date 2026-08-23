from datetime import datetime, timezone

from signal_engine.engine import build_entity_table
from signal_engine.entities import ENTITIES
from signal_engine.scoring import Signal

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _sig(ticker, source, severity, confidence):
    return Signal(ticker, source, "test", severity, confidence, NOW, "https://example.invalid")


def test_every_entity_gets_a_row_even_with_zero_signals():
    results = build_entity_table([], half_life_days=30, now=NOW)
    tickers = {r.ticker for r in results}
    assert tickers == {e.ticker for e in ENTITIES}
    assert all(r.composite_score == 0.0 for r in results)


def test_ranking_is_descending_by_composite_score():
    signals = [
        _sig("CRM", "sec", 90, 0.95),
        _sig("HUBS", "hn", 20, 0.60),
    ]
    results = build_entity_table(signals, half_life_days=30, now=NOW)
    scored = [r for r in results if r.signal_count > 0]
    assert scored[0].ticker == "CRM"
    assert scored == sorted(scored, key=lambda r: r.composite_score, reverse=True)


def test_corroboration_across_sources_outranks_a_single_source():
    single_source = [_sig("OKTA", "hn", 60, 0.60)]
    two_sources = [_sig("ZS", "hn", 60, 0.60), _sig("ZS", "github", 60, 0.90)]
    results = build_entity_table(single_source + two_sources, half_life_days=30, now=NOW)
    okta = next(r for r in results if r.ticker == "OKTA")
    zs = next(r for r in results if r.ticker == "ZS")
    assert zs.composite_score > okta.composite_score
    assert zs.by_source == {"hn": 1, "github": 1}


def test_by_source_counts_are_accurate():
    signals = [_sig("CRM", "sec", 50, 0.95), _sig("CRM", "sec", 40, 0.95), _sig("CRM", "hn", 30, 0.60)]
    results = build_entity_table(signals, half_life_days=30, now=NOW)
    crm = next(r for r in results if r.ticker == "CRM")
    assert crm.by_source == {"sec": 2, "hn": 1}
    assert crm.signal_count == 3
