"""Spearman rank correlation, stdlib only (no numpy/scipy dependency for
one function). This module has nothing to do with whether real reply data
exists yet -- it's pure math, tested against synthetic fixtures purely to
prove the arithmetic is right. Whether the composite score in this repo
actually predicts anything is a completely separate, currently-unanswered
question -- see scripts/correlate_with_replies.py and the README.
"""

from __future__ import annotations


def _rank(values: list[float]) -> list[float]:
    """Average (fractional) ranks, so tied values share a rank instead of
    an arbitrary tie-break deciding the result."""
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1  # 1-indexed
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman's rho. Returns None (not 0.0) when undefined -- either input
    list is empty/mismatched, or either series has zero variance (every
    value tied), in which case a correlation coefficient has no meaning and
    reporting 0.0 would misleadingly read as 'measured no relationship'
    rather than 'not computable.' Same discipline as
    gtm_eval.metrics.precision/recall returning None for undefined cases."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx, ry = _rank(xs), _rank(ys)
    n = len(xs)
    mean_r = (n + 1) / 2.0
    num = sum((rx[i] - mean_r) * (ry[i] - mean_r) for i in range(n))
    denom_x = sum((r - mean_r) ** 2 for r in rx)
    denom_y = sum((r - mean_r) ** 2 for r in ry)
    if denom_x == 0 or denom_y == 0:
        return None
    return num / (denom_x * denom_y) ** 0.5
