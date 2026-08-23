"""SEC EDGAR full text search -- real, free, no API key.

Endpoint verified live on 2026-08-23: https://efts.sec.gov/LATEST/search-index
SEC's fair-access policy asks for a descriptive User-Agent identifying the
requester; that's the only header this needs.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from ..retry import retry_with_backoff
from ..scoring import SEC_ITEM_SEVERITY, SEC_ITEM_SEVERITY_DEFAULT, SEC_CONFIDENCE, Signal

USER_AGENT = "gtm-signal-engine-research adityachouhan5555@gmail.com"
BASE = "https://efts.sec.gov/LATEST/search-index"


def _filing_index_url(cik: str, adsh: str) -> str:
    """Standard EDGAR filing-index URL, built from CIK + accession number --
    no extra API call needed. Verified live against a real filing on
    2026-08-23 (see README)."""
    cik_int = str(int(cik))  # strip leading zeros
    adsh_nodash = adsh.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{adsh_nodash}/{adsh}-index.htm"


def fetch_8k_filings(cik: str, start_date: str, end_date: str, timeout: int = 20) -> list[dict]:
    """Raw filing hits for one CIK's 8-K filings in [start_date, end_date]
    (YYYY-MM-DD). One HTTP call. Returns SEC's own hit records unmodified."""
    params = {
        "q": '""',
        "forms": "8-K",
        "ciks": cik,
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
    }
    def _do_request():
        resp = requests.get(BASE, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("hits", {}).get("hits", [])

    # SEC's search-index has been observed to 500 transiently (confirmed
    # by hand: an identical retried request succeeded every time) -- see
    # retry.py's docstring for the real incident this responds to.
    return retry_with_backoff(_do_request)


def filing_to_signal(ticker: str, hit: dict) -> Signal | None:
    """One filing may disclose multiple 8-K items; severity is the max
    across the items it discloses (a filing's severity is driven by its
    single most consequential disclosed item, not diluted by a
    companion exhibit-only item like 9.01 on the same filing)."""
    src = hit["_source"]
    items = src.get("items") or []
    if not items:
        return None
    severities = [SEC_ITEM_SEVERITY.get(i, SEC_ITEM_SEVERITY_DEFAULT) for i in items]
    severity = max(severities)
    driving_item = items[severities.index(severity)]
    file_date = src["file_date"]
    observed_at = datetime.strptime(file_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cik = src["ciks"][0]
    adsh = src["adsh"]
    return Signal(
        ticker=ticker,
        source="sec",
        event_type=f"8-K item {driving_item}",
        severity=severity,
        confidence=SEC_CONFIDENCE,
        observed_at=observed_at,
        evidence_url=_filing_index_url(cik, adsh),
    )


def fetch_signals_for_entity(ticker: str, cik: str, start_date: str, end_date: str,
                              sleep_between_calls: float = 0.5) -> list[Signal]:
    hits = fetch_8k_filings(cik, start_date, end_date)
    time.sleep(sleep_between_calls)  # SEC fair-access pacing
    signals = []
    for hit in hits:
        sig = filing_to_signal(ticker, hit)
        if sig is not None:
            signals.append(sig)
    return signals
