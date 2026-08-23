"""GitHub REST + Search APIs -- real, free, unauthenticated (rate-limited:
60 req/hr on the core API, 10 req/min on Search -- both verified live on
2026-08-23, see README).

Flagship-repo selection rule, stated once here rather than picked by hand
per org: the org's highest-starred public repository. Non-arbitrary, and
re-derivable by anyone re-running this script -- not "whichever repo looked
representative to me."
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from ..retry import retry_with_backoff
from ..scoring import GITHUB_CONFIDENCE, Signal

SEARCH = "https://api.github.com/search/repositories"
API = "https://api.github.com"


def select_flagship_repo(org: str, timeout: int = 20) -> tuple[str, int]:
    """Returns (full_name, stargazer_count) of the org's highest-starred
    public repo. Raises if the org has zero public repos (would indicate a
    stale/renamed org -- a real condition worth failing loudly on, not
    masking).

    Wrapped in retry_with_backoff: a live run on 2026-08-23 hit a run of
    transient connection resets and SSL EOF errors against both
    api.github.com and hn.algolia.com in the same window, while a plain
    curl loop against the same host succeeded 5/5 immediately after --
    consistent with a transient network blip, not a server-side outage.
    requests.exceptions.SSLError subclasses ConnectionError, so it's
    already covered by retry.py's default retry_on tuple."""
    def _do_request():
        resp = requests.get(
            SEARCH, params={"q": f"org:{org}", "sort": "stars", "order": "desc", "per_page": 1},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])

    items = retry_with_backoff(_do_request)
    if not items:
        raise ValueError(f"org '{org}' has no public repositories -- check the org still exists")
    top = items[0]
    return top["full_name"], top["stargazers_count"]


def fetch_releases(full_name: str, timeout: int = 20) -> list[dict]:
    """Up to 100 most recent releases. Most of these orgs' flagship repos
    release far less often than 100 times in a year, so one page is enough
    to cover the 180-day window this artifact scores against; a repo that
    releases fast enough to fill 100 slots inside 180 days would need
    pagination, which this does not implement -- a stated, not hidden,
    limitation."""
    def _do_request():
        resp = requests.get(f"{API}/repos/{full_name}/releases", params={"per_page": 100}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    return retry_with_backoff(_do_request)


def _release_severity(current_count: int, prior_count: int) -> float:
    """Severity centered on 50 = 'no change in release cadence.' Faster
    cadence (more releases in the trailing window than the prior one)
    pushes toward 100; slower pushes toward 0; a swing of +/-100% or more
    saturates at the boundary. If there were zero releases in the prior
    window too, cadence can't be expressed as a percent change of zero --
    severity is instead a direct, capped function of the new volume alone
    (going from silence to any releases is itself the signal)."""
    if prior_count == 0:
        return min(100.0, current_count * 20.0)
    pct_change = (current_count - prior_count) / prior_count
    severity = 50.0 + pct_change * 50.0
    return max(0.0, min(100.0, severity))


def releases_to_signal(ticker: str, full_name: str, releases: list[dict],
                        now: datetime | None = None) -> Signal | None:
    now = now or datetime.now(timezone.utc)
    dates = []
    for r in releases:
        ts = r.get("published_at")
        if ts:
            dates.append(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))

    def age_days(d):
        return (now - d).total_seconds() / 86400.0

    current = [d for d in dates if age_days(d) <= 90]
    prior = [d for d in dates if 90 < age_days(d) <= 180]

    if not current and not prior:
        return None  # nothing observable in either window -- no signal to emit, not a zero one

    severity = _release_severity(len(current), len(prior))
    most_recent = max(dates) if dates else now
    return Signal(
        ticker=ticker,
        source="github",
        event_type=f"release_cadence_change ({len(current)} in trailing 90d vs {len(prior)} in prior 90d)",
        severity=severity,
        confidence=GITHUB_CONFIDENCE,
        observed_at=most_recent,
        evidence_url=f"https://github.com/{full_name}/releases",
    )


def fetch_signal_for_entity(ticker: str, org: str, sleep_after_search: float = 6.5) -> Signal | None:
    full_name, _ = select_flagship_repo(org)
    time.sleep(sleep_after_search)  # Search API is 10/min unauthenticated; pace to stay under it
    releases = fetch_releases(full_name)
    return releases_to_signal(ticker, full_name, releases)
