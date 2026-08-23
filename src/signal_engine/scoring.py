"""Composite Severity x Confidence x Recency signal scoring, with a
documented, non-arbitrary rubric for each source, and a cross-source
aggregation rule chosen for a specific, stated reason.

Every constant below is explained where it's defined. None of it is a
tuned-to-look-good number -- there is nothing to tune against yet, since
this artifact's own honesty test (correlating composite score against real
reply rates) is blocked on artifact 5's sequencing infrastructure not
existing. See scripts/correlate_with_replies.py and the README's "What
this doesn't prove" section.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isnan


@dataclass(frozen=True)
class Signal:
    ticker: str          # canonical entity key, from entities.py
    source: str          # "sec" | "github" | "hn"
    event_type: str      # source-specific event/category label
    severity: float       # 0-100, source-specific rubric (see below)
    confidence: float     # 0-1, source's structural reliability
    observed_at: datetime  # timezone-aware
    evidence_url: str     # a real, dereferenceable link to the source record


# --- Recency ----------------------------------------------------------------

def decay_weight(days_old: float, half_life_days: float) -> float:
    """Exponential decay: weight halves every `half_life_days`.

    A signal exactly `half_life_days` old scores 0.5; two half-lives, 0.25.
    This is the standard decay form (matches radioactive decay / most
    information-recency models) chosen over linear decay because it never
    goes negative and never needs a hard cutoff -- old signals fade toward
    zero rather than being truncated at an arbitrary age.

    Raises on a negative age (a signal timestamped in the future) rather
    than silently clamping it, since that can only mean a clock-skew or
    parsing bug upstream, not a real data condition.
    """
    if days_old < 0:
        raise ValueError(f"signal is timestamped in the future ({days_old} days old)")
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    return 0.5 ** (days_old / half_life_days)


def days_since(observed_at: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    return (now - observed_at).total_seconds() / 86400.0


# --- Severity rubrics, one per source ---------------------------------------

# SEC 8-K item codes -> severity, ranked by what the item itself discloses.
# Item numbers and their meanings are SEC's own (Regulation S-K / Form 8-K
# instructions), not invented here -- only the relative severity ranking is
# a judgment call, and it's ranked by "how much does this item structurally
# imply near-term operational or leadership change," a defensible read of
# the item definitions themselves:
SEC_ITEM_SEVERITY = {
    "1.03": 95,  # Bankruptcy or receivership
    "4.01": 80,  # Changes in accountant -- frequently a distress signal
    "2.01": 75,  # Completion of acquisition/disposition of assets
    "5.02": 70,  # Departure/election of directors or officers
    "1.02": 65,  # Termination of a material definitive agreement
    "2.06": 60,  # Material impairments
    "7.01": 35,  # Regulation FD disclosure -- routine, often just an investor deck
    "8.01": 40,  # Other events -- catch-all, genuinely ambiguous severity
    "9.01": 15,  # Financial statements and exhibits -- procedural, near-zero signal alone
}
SEC_ITEM_SEVERITY_DEFAULT = 30  # an item code not in the table above: unknown, treated as low-signal rather than dropped
SEC_CONFIDENCE = 0.95  # CIK-keyed to one legal entity; essentially no ambiguity

# GitHub: severity from a trailing-90-day release count relative to the
# entity's own prior 90-day window, not an absolute count (an absolute
# release count means nothing without a baseline -- "12 releases" is
# unremarkable for one org and a step-change for another).
GITHUB_CONFIDENCE = 0.90  # org slug is an unambiguous identifier

# HN: severity from the story's own point count. This is not invented --
# it's the real, already-crowd-judged importance signal HN itself produces.
HN_CONFIDENCE = 0.60  # weakest link: name-string alias matching, see entities.py
                       # and README for the real false-positive risk this carries


def score_signal(sig: Signal, half_life_days: float, now: datetime | None = None) -> float:
    """Per-signal composite: (severity/100) * confidence * recency-decay, in [0, 1]."""
    normalized_severity = sig.severity / 100.0
    if not (0.0 <= normalized_severity <= 1.0):
        raise ValueError(f"severity out of range 0-100: {sig.severity}")
    if not (0.0 <= sig.confidence <= 1.0):
        raise ValueError(f"confidence out of range 0-1: {sig.confidence}")
    weight = decay_weight(days_since(sig.observed_at, now), half_life_days)
    value = normalized_severity * sig.confidence * weight
    if isnan(value):
        raise ValueError(f"scoring produced NaN for signal {sig}")
    return value


def aggregate_entity_score(signal_scores: list[float]) -> float:
    """Combine multiple per-signal scores (already in [0,1]) into one
    entity-level score, also in [0,1].

    Chosen rule: noisy-OR, i.e. 1 - product(1 - s_i), NOT a sum and NOT a
    max. Reasoning:

    - A plain sum rewards pure volume from a single noisy source (e.g. ten
      unrelated HN mentions could outscore one confirmed SEC bankruptcy
      filing) -- wrong, since HN confidence is deliberately the lowest of
      the three.
    - A plain max ignores exactly the thing multi-source fusion is supposed
      to capture: two independent sources corroborating the same entity is
      real additional evidence, not redundant noise, and should score
      higher than either alone.
    - Noisy-OR treats each signal as independent evidence that the entity is
      "worth prioritizing," and combines them the way independent
      probabilities of at least one true condition combine. It saturates
      toward 1.0 as corroboration accumulates, without a single
      high-severity, high-confidence signal ever being drowned out by many
      weak ones (unlike a sum).

    This has not been validated against real outcomes -- see the module
    docstring. It's the documented, defensible starting rule, not a proven
    one.
    """
    if not signal_scores:
        return 0.0
    product_of_complements = 1.0
    for s in signal_scores:
        if not (0.0 <= s <= 1.0):
            raise ValueError(f"signal score out of range 0-1: {s}")
        product_of_complements *= (1.0 - s)
    return 1.0 - product_of_complements
