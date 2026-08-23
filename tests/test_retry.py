import pytest
import requests

from signal_engine.retry import retry_with_backoff


def test_succeeds_immediately_without_retrying():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert retry_with_backoff(fn, attempts=3, base_delay=0.0) == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise requests.exceptions.ConnectionError("transient")
        return "ok"

    assert retry_with_backoff(fn, attempts=5, base_delay=0.0) == "ok"
    assert len(calls) == 3


def test_exhausts_attempts_and_raises_last_exception():
    calls = []

    def fn():
        calls.append(1)
        raise requests.exceptions.HTTPError("still failing")

    with pytest.raises(requests.exceptions.HTTPError, match="still failing"):
        retry_with_backoff(fn, attempts=3, base_delay=0.0)
    assert len(calls) == 3  # exhausted all attempts, didn't give up early or retry forever


def test_does_not_retry_unrelated_exceptions():
    def fn():
        raise ValueError("not a retryable network error")

    with pytest.raises(ValueError):
        retry_with_backoff(fn, attempts=3, base_delay=0.0)
