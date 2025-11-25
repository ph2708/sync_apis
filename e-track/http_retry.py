#!/usr/bin/env python3
"""Small HTTP helper with retries and backoff for e-track collector.

Does not add external dependencies; uses simple exponential backoff.
"""
import time
import logging
from typing import Any, Optional
import random
import requests

LOG = logging.getLogger('e-track.http_retry')


def post_with_retries(session: requests.Session, url: str, auth: Optional[Any] = None, json: Optional[dict] = None,
                      timeout: Any = (10, 60), max_attempts: int = 4, backoff_factor: float = 0.5):
    """POST with simple retry/backoff.

    timeout: either a single number (total timeout) or a (connect, read) tuple. Default is (10, 60).
    Retries on network errors, timeouts, and 5xx responses. For 429 will also backoff.
    Raises the final exception or returns the successful Response.
    """
    attempt = 0
    # normalize timeout: if a single number is provided, treat it as the total/read timeout
    # and use a smaller connect timeout to fail fast on connection issues.
    if isinstance(timeout, (int, float)):
        total_timeout = float(timeout)
        connect_timeout = 10.0 if total_timeout > 10.0 else total_timeout
        timeout = (connect_timeout, total_timeout)
    while True:
        attempt += 1
        try:
            resp = session.post(url, auth=auth, json=json, timeout=timeout)
        except Exception as e:
            # log exception class to help distinguish connect vs read timeouts
            LOG.warning('Request exception attempt %d for %s: %s (%s)', attempt, url, type(e).__name__, e)
            if attempt >= max_attempts:
                LOG.exception('Max attempts reached for %s', url)
                raise
            # add a small jitter to avoid thundering herds
            sleep = backoff_factor * (2 ** (attempt - 1))
            sleep = sleep * (1.0 + random.random() * 0.2)
            time.sleep(sleep)
            continue

        # if response is 429 or 5xx, retry
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            LOG.warning('Retryable status %d for %s (attempt %d)', resp.status_code, url, attempt)
            if attempt >= max_attempts:
                try:
                    resp.raise_for_status()
                finally:
                    return resp
            # on 429, try longer wait
            if resp.status_code == 429:
                sleep = backoff_factor * (2 ** (attempt - 1)) + 1.0
            else:
                sleep = backoff_factor * (2 ** (attempt - 1))
            sleep = sleep * (1.0 + random.random() * 0.2)
            time.sleep(sleep)
            continue

        return resp
