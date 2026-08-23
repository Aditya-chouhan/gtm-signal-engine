"""Hacker News via the Algolia Search API -- real, free, no key.
Endpoint verified live on 2026-08-23: https://hn.algolia.com/api/v1/search
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..dedup import resolve_hn_text
from ..retry import retry_with_backoff
from ..scoring import HN_CONFIDENCE, Signal

BASE = "https://hn.algolia.com/api/v1/search"


def _parse_hn_timestamp(raw: str | None) -> datetime:
    """Algolia's created_at is inconsistently formatted across hits: some
    carry fractional seconds ('...08.123Z'), some don't ('...08Z') --
    found by a real test failure against a captured fixture, not assumed
    up front. Falls back to now() only if the field is missing entirely,
    which would itself be a data-quality signal worth not hiding behind a
    parse crash."""
    if not raw:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unrecognized HN timestamp format: {raw!r}")


def fetch_stories(query: str, days_back: int = 180, hits_per_page: int = 50,
                   timeout: int = 20) -> list[dict]:
    """Story-tagged hits mentioning `query`, newest-first. One HTTP call.
    numericFilters restricts to the trailing window server-side, so this
    isn't fetching-then-discarding -- fewer, more relevant hits come back."""
    cutoff = int(datetime.now(timezone.utc).timestamp()) - days_back * 86400

    def _do_request():
        resp = requests.get(
            BASE,
            params={
                "query": query,
                "tags": "story",
                "hitsPerPage": hits_per_page,
                "numericFilters": f"created_at_i>{cutoff}",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("hits", [])

    # See github_source.select_flagship_repo's docstring for the real
    # incident (2026-08-23) that motivated wrapping every network call in
    # this project with retry_with_backoff, not just SEC's.
    return retry_with_backoff(_do_request)


def hit_to_signal(hit: dict) -> Signal | None:
    """Resolves the hit's title back to exactly one entity (see dedup.py);
    returns None (not a zero-severity signal) if resolution fails, so
    callers can count real drops instead of quietly scoring noise."""
    title = hit.get("title") or ""
    ticker = resolve_hn_text(title)
    if ticker is None:
        return None
    points = hit.get("points") or 0
    severity = min(100.0, float(points))  # HN's own crowd-judged importance signal, not invented
    observed_at = _parse_hn_timestamp(hit.get("created_at"))
    story_id = hit.get("objectID")
    return Signal(
        ticker=ticker,
        source="hn",
        event_type=f"hn_story (points={points})",
        severity=severity,
        confidence=HN_CONFIDENCE,
        observed_at=observed_at,
        evidence_url=f"https://news.ycombinator.com/item?id={story_id}",
    )


def fetch_signals_for_query(query: str, days_back: int = 180) -> tuple[list[Signal], dict]:
    """Returns (resolved signals, drop-count stats) -- the stats are part of
    the return value on purpose, not a side log line, so a caller can't
    forget to report them."""
    hits = fetch_stories(query, days_back=days_back)
    signals, no_match, ambiguous_or_other_entity = [], 0, 0
    for hit in hits:
        sig = hit_to_signal(hit)
        if sig is None:
            no_match += 1
        else:
            signals.append(sig)
    stats = {"hits_returned": len(hits), "resolved": len(signals), "dropped": no_match}
    return signals, stats
