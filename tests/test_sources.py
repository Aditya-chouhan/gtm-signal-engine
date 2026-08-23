"""Offline parsing tests against real, committed API response fixtures
(fixtures/*.json -- captured live on 2026-08-23, see README). No network
calls happen in this test file; that's the point of committing the
fixtures rather than hitting the live APIs on every test run.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from signal_engine.sources.sec_source import filing_to_signal
from signal_engine.sources.github_source import releases_to_signal
from signal_engine.sources.hn_source import hit_to_signal, _parse_hn_timestamp

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXED_NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_sec_fixture_parses_into_valid_signals():
    hits = _load("sec_sample_salesforce.json")["hits"]["hits"]
    assert len(hits) > 0, "fixture is empty -- was it captured correctly?"
    signals = [s for s in (filing_to_signal("CRM", h) for h in hits) if s is not None]
    assert len(signals) > 0
    for sig in signals:
        assert sig.ticker == "CRM"
        assert sig.source == "sec"
        assert 0 <= sig.severity <= 100
        assert sig.confidence == 0.95
        assert sig.evidence_url.startswith("https://www.sec.gov/Archives/edgar/data/1108524/")


def test_sec_fixture_real_filing_has_item_502_officer_departure():
    # This specific filing was inspected by hand while building this module
    # (see README build log) -- a real 8-K, item 5.02, filed 2026-06-02.
    hits = _load("sec_sample_salesforce.json")["hits"]["hits"]
    matching = [h for h in hits if h["_source"]["file_date"] == "2026-06-02"]
    assert matching, "expected filing not present -- fixture may be stale, regenerate it"
    sig = filing_to_signal("CRM", matching[0])
    assert sig.event_type == "8-K item 5.02"
    assert sig.severity == 70


def test_github_fixture_produces_bounded_severity():
    releases = _load("github_sample_lwc_releases.json")
    sig = releases_to_signal("CRM", "salesforce/lwc", releases, now=FIXED_NOW)
    assert sig is not None
    assert 0 <= sig.severity <= 100
    assert sig.confidence == 0.90
    assert sig.evidence_url == "https://github.com/salesforce/lwc/releases"


def test_github_no_releases_in_either_window_yields_no_signal():
    # An org whose only releases are all >180 days old should not be scored
    # -- silence isn't the same as a zero severity, it's "nothing observed."
    ancient = [{"published_at": "2020-01-01T00:00:00Z"}]
    assert releases_to_signal("XXX", "someone/somewhere", ancient, now=FIXED_NOW) is None


def test_hn_timestamp_parses_both_observed_formats():
    # A real fixture hit ('2017-02-23T23:05:08Z') has no fractional seconds
    # while others do -- this test exists because that inconsistency broke
    # the parser on the first run against real data.
    with_frac = _parse_hn_timestamp("2026-08-20T12:00:00.123Z")
    without_frac = _parse_hn_timestamp("2017-02-23T23:05:08Z")
    assert with_frac.year == 2026
    assert without_frac.year == 2017


def test_hn_fixture_resolved_hits_are_all_cloudflare():
    hits = _load("hn_sample_cloudflare.json")["hits"]
    signals = [s for s in (hit_to_signal(h) for h in hits) if s is not None]
    # Not every hit necessarily mentions Cloudflare by name in the title
    # (Algolia's search matches body/URL text too) -- so len(signals) <=
    # len(hits) is expected, not a bug. Every *resolved* signal must be
    # correctly attributed, which is the actual thing under test.
    assert len(signals) <= len(hits)
    for sig in signals:
        assert sig.ticker == "NET"
        assert sig.source == "hn"
        assert sig.confidence == 0.60
        assert 0 <= sig.severity <= 100
