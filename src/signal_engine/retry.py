"""Retry with exponential backoff -- added after a real failure, not
speculatively. During this repo's first live fetch run (2026-08-23),
SEC's full-text search API returned a bare 500 for 3 of 14 entities
(SNOW, ASAN, MNDY). Manually re-issuing the exact same failing request
seconds later succeeded every time -- confirmed transient, not a bug in
the request itself (see README's "What broke" section). This module is
the fix: retry the same request a bounded number of times before giving
up for real, instead of a script that fetches 14 entities and silently
returns 11.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

import requests

T = TypeVar("T")


def retry_with_backoff(fn: Callable[[], T], *, attempts: int = 3,
                        base_delay: float = 2.0,
                        retry_on: tuple = (requests.exceptions.HTTPError,
                                            requests.exceptions.ConnectionError,
                                            requests.exceptions.Timeout)) -> T:
    """Calls fn() up to `attempts` times, sleeping base_delay * 2**i between
    tries. Re-raises the last exception if every attempt fails -- a caller
    that wants to keep processing other entities must catch that itself
    (see scripts/fetch_live_signals.py, which does exactly that per entity
    rather than letting one bad entity kill the whole run)."""
    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as exc:
            last_exc = exc
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
    raise last_exc
