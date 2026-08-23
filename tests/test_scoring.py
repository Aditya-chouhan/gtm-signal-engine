from datetime import datetime, timedelta, timezone

import pytest

from signal_engine.scoring import (
    Signal, decay_weight, days_since, score_signal, aggregate_entity_score,
    SEC_ITEM_SEVERITY, SEC_ITEM_SEVERITY_DEFAULT,
)


def test_decay_weight_at_zero_days_is_one():
    assert decay_weight(0, half_life_days=30) == 1.0


def test_decay_weight_at_one_half_life_is_half():
    assert decay_weight(30, half_life_days=30) == pytest.approx(0.5)


def test_decay_weight_at_two_half_lives_is_quarter():
    assert decay_weight(60, half_life_days=30) == pytest.approx(0.25)


def test_decay_weight_rejects_future_timestamp():
    with pytest.raises(ValueError, match="future"):
        decay_weight(-1, half_life_days=30)


def test_decay_weight_rejects_nonpositive_half_life():
    with pytest.raises(ValueError):
        decay_weight(10, half_life_days=0)


def test_days_since_matches_manual_delta():
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    then = now - timedelta(days=12, hours=12)
    assert days_since(then, now) == pytest.approx(12.5)


def _sig(severity=70.0, confidence=0.9, days_old=0.0, now=None):
    now = now or datetime(2026, 8, 23, tzinfo=timezone.utc)
    return Signal(
        ticker="TEST", source="sec", event_type="test",
        severity=severity, confidence=confidence,
        observed_at=now - timedelta(days=days_old),
        evidence_url="https://example.invalid",
    ), now


def test_score_signal_full_marks_at_zero_age():
    sig, now = _sig(severity=100.0, confidence=1.0, days_old=0.0)
    assert score_signal(sig, half_life_days=30, now=now) == pytest.approx(1.0)


def test_score_signal_decays_with_age():
    sig, now = _sig(severity=100.0, confidence=1.0, days_old=30.0)
    assert score_signal(sig, half_life_days=30, now=now) == pytest.approx(0.5)


def test_score_signal_rejects_out_of_range_severity():
    sig, now = _sig(severity=150.0)
    with pytest.raises(ValueError, match="severity"):
        score_signal(sig, half_life_days=30, now=now)


def test_score_signal_rejects_out_of_range_confidence():
    sig, now = _sig(confidence=1.5)
    with pytest.raises(ValueError, match="confidence"):
        score_signal(sig, half_life_days=30, now=now)


def test_aggregate_empty_is_zero():
    assert aggregate_entity_score([]) == 0.0


def test_aggregate_single_signal_equals_itself():
    assert aggregate_entity_score([0.42]) == pytest.approx(0.42)


def test_aggregate_two_signals_exceeds_either_alone():
    # This is the whole point of noisy-OR over max: two weak-ish
    # independent signals should out-rank either one in isolation.
    combined = aggregate_entity_score([0.3, 0.3])
    assert combined > 0.3
    assert combined == pytest.approx(1 - (1 - 0.3) * (1 - 0.3))


def test_aggregate_never_exceeds_one():
    combined = aggregate_entity_score([0.9, 0.9, 0.9, 0.9])
    assert combined < 1.0


def test_aggregate_rejects_out_of_range_score():
    with pytest.raises(ValueError):
        aggregate_entity_score([1.2])


def test_sec_item_severity_table_ranks_bankruptcy_above_exhibits_only():
    # Sanity check on the rubric itself, not just the arithmetic around it.
    assert SEC_ITEM_SEVERITY["1.03"] > SEC_ITEM_SEVERITY["9.01"]


def test_sec_item_severity_default_is_below_the_documented_items():
    # An unlisted item code shouldn't silently outrank the items that were
    # actually reasoned about.
    assert SEC_ITEM_SEVERITY_DEFAULT < max(SEC_ITEM_SEVERITY.values())
