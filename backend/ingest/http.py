"""Shared retrying HTTP client (BUILD_SPEC §1.3).

Retry 3x with exponential backoff (2s / 8s / 30s), honoring Retry-After and
rate-limit reset headers. After exhaustion, raise HttpError; callers decide
whether the resource is blocking (HALT) or non-blocking (degrade + continue).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger("vayunetra.http")

RETRY_WAITS = [2, 8, 30]  # seconds between attempts (exponential-ish)
DEFAULT_TIMEOUT = 60.0
# Some providers (Overpass mirrors) reject requests without a descriptive UA.
USER_AGENT = "VayuNetra/1.0 (urban air-quality research; +https://vayunetra.local)"


class HttpError(RuntimeError):
    """Raised after all retries are exhausted."""


def _retry_after_seconds(resp: httpx.Response, planned: float) -> float:
    """Honor Retry-After / x-ratelimit-reset headers; fall back to planned wait."""
    for header in ("Retry-After", "retry-after", "x-ratelimit-reset", "X-RateLimit-Reset"):
        val = resp.headers.get(header)
        if val:
            try:
                return max(float(val), planned)
            except ValueError:
                continue
    return planned


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: Any = None,
    timeout: float = DEFAULT_TIMEOUT,
    expected_status: tuple[int, ...] = (200,),
) -> httpx.Response:
    """Perform an HTTP request with bounded retries. Raise HttpError on failure."""
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    last_exc: Exception | None = None
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            resp = httpx.request(
                method, url, headers=merged_headers, params=params, data=data, timeout=timeout
            )
            if resp.status_code in expected_status:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < len(RETRY_WAITS):
                wait = _retry_after_seconds(resp, RETRY_WAITS[attempt])
                log.warning("%s %s -> %s; retrying in %.0fs", method, url, resp.status_code, wait)
                time.sleep(wait)
                continue
            raise HttpError(f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:200]}")
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < len(RETRY_WAITS):
                wait = RETRY_WAITS[attempt]
                log.warning("%s %s failed (%s); retrying in %.0fs", method, url, exc, wait)
                time.sleep(wait)
                continue
            raise HttpError(f"{method} {url} failed after retries: {exc}") from exc
    raise HttpError(f"{method} {url} failed after retries: {last_exc}")


def get_json(url: str, **kwargs: Any) -> Any:
    return request("GET", url, **kwargs).json()


def get_text(url: str, **kwargs: Any) -> str:
    return request("GET", url, **kwargs).text


def post_text(url: str, **kwargs: Any) -> str:
    return request("POST", url, **kwargs).text
