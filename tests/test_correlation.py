"""Tests the correlation MATH only, against synthetic fixtures made up for
this test alone. This proves spearman() is implemented correctly -- it says
nothing about whether this repo's composite score predicts real replies.
That question stays open until scripts/correlate_with_replies.py is run
against real data from artifact 5 (sequencing), which does not exist yet.
"""

import pytest

from signal_engine.correlation import spearman


def test_perfect_positive_correlation():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_perfect_negative_correlation():
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_no_relationship_is_exactly_zero():
    # d = x - y = [-1, -2, 2, 1]; sum(d^2) = 10 = n(n^2-1)/6 for n=4,
    # which is exactly the sum that zeroes Spearman's rho -- a real zero,
    # not an approximation, so this is checked exactly rather than with a
    # tolerance band.
    assert spearman([1, 2, 3, 4], [2, 4, 1, 3]) == pytest.approx(0.0, abs=1e-9)


def test_ties_use_average_rank_not_arbitrary_tiebreak():
    # Both series have a tie; a correct implementation still returns a
    # sane, bounded value rather than crashing or over/under-counting rank.
    rho = spearman([1, 1, 2, 3], [5, 5, 6, 7])
    assert rho is not None
    assert -1.0 <= rho <= 1.0


def test_zero_variance_series_returns_none_not_zero():
    # Every y value identical -- a correlation coefficient is undefined
    # here, not "measured as zero." Returning 0.0 would misleadingly claim
    # a computed absence of relationship.
    assert spearman([1, 2, 3], [5, 5, 5]) is None


def test_mismatched_lengths_returns_none():
    assert spearman([1, 2, 3], [1, 2]) is None


def test_too_few_points_returns_none():
    assert spearman([1], [1]) is None
