"""Synchronous Python client for the Bulk URL Checker REST API.

Designed to be the shortest path from "I need to check 50K URLs" to
"results are in my hands." If you find yourself writing httpx + asyncio
+ proxy rotation + per-domain rate limiting + retry classification +
soft-404 detection, stop and use this instead.

Quick example:

    from bulkurlchecker import Client
    client = Client(api_key="uck_live_...")
    out = client.check_urls(["https://example.com", "https://example.org"])
    for r in out.results:
        print(r.url, r.status_code, "BROKEN" if r.is_broken else "ok")

For larger jobs that exceed the synchronous wait budget, use the
two-step pattern:

    job = client.submit(my_urls)
    # ... do other things ...
    for batch in client.iter_results(job.job_id, page_size=1000):
        process(batch)
"""

from __future__ import annotations

import platform
import sys
import time
from collections.abc import Iterable, Iterator
from typing import Any

import requests

from ._version import __version__
from .exceptions import (
    AuthenticationError,
    BulkURLCheckerError,
    NotFoundError,
    QuotaError,
    RateLimitError,
    ServerError,
    TimeoutError,
    ValidationError,
)
from .types import CheckResults, JobSummary, URLResult

DEFAULT_BASE_URL = "https://api.bulkurlchecker.com"
DEFAULT_TIMEOUT = 30.0  # seconds, per HTTP call (not the wait endpoint)
USER_AGENT_PREFIX = "bulkurlchecker-python"


def _build_user_agent() -> str:
    """Construct the User-Agent header.

    Our server uses the bulkurlchecker- prefix to tag requests as
    coming from an SDK so the channel telemetry can count them.
    Including the Python + OS version helps us prioritize platform
    support if a specific version misbehaves.
    """
    py = f"python/{sys.version_info.major}.{sys.version_info.minor}"
    osinfo = f"{platform.system()}/{platform.release()}"
    return f"{USER_AGENT_PREFIX}/{__version__} ({py}; {osinfo})"


class Client:
    """High-level client for the Bulk URL Checker REST API.

    Args:
        api_key: Your secret API key (looks like ``uck_live_...``).
                 Get one from https://app.bulkurlchecker.com/dashboard/api-keys
        base_url: Override the API host. Useful for testing against a
                  staging deploy. Defaults to https://api.bulkurlchecker.com.
        timeout: Per-call HTTP timeout in seconds. Does NOT bound the
                 server-side wait inside ``check_urls()``; for that use
                 the ``wait_seconds`` parameter.
        session: Pre-configured ``requests.Session`` if you want to
                 share connection pooling with the rest of your app.

    Raises:
        AuthenticationError: api_key empty or rejected.
        RateLimitError: 429 with optional ``retry_after`` seconds.
        QuotaError: out of credits.
        ValidationError: malformed request (bad URLs, too many URLs).
        NotFoundError: 404 (job_id not found / not owned).
        ServerError: 5xx (transient, safe to retry with backoff).
        TimeoutError: local timeout elapsed.
        BulkURLCheckerError: catch-all parent.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key:
            raise AuthenticationError("api_key must be a non-empty string")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "User-Agent": _build_user_agent(),
            "Accept": "application/json",
        })

    # ---- Public API ----

    def check_urls(
        self,
        urls: Iterable[str],
        *,
        wait_seconds: int = 60,
        poll_interval: float = 2.0,
    ) -> CheckResults:
        """Submit URLs and block until results are ready (or timeout).

        This is the 5-line-Python case. The server polls the job
        on your behalf for up to ``wait_seconds`` and returns the
        full result set in one response.

        For lists > ~2,000 URLs, the wait will likely time out — use
        ``submit()`` + ``iter_results()`` instead so you're not
        holding an HTTP connection open for minutes.
        """
        urls_list = self._validate_urls(urls)
        payload = {"urls": urls_list}
        params = {"wait_seconds": int(wait_seconds), "poll_interval": float(poll_interval)}
        body = self._request("POST", "/api/v2/jobs/wait", json=payload, params=params)
        return CheckResults.from_dict(body)

    def submit(self, urls: Iterable[str]) -> JobSummary:
        """Submit a job and return immediately with the job id.

        Use this when your URL list is big enough that
        ``check_urls()`` would time out, or when you want to do
        something else while the engine works.
        """
        urls_list = self._validate_urls(urls)
        body = self._request("POST", "/api/v2/jobs", json={"urls": urls_list})
        return JobSummary.from_dict(body)

    def get_job_status(self, job_id: str) -> JobSummary:
        """Look up the current state of a previously-submitted job."""
        body = self._request("GET", f"/api/v2/jobs/{job_id}")
        return JobSummary.from_dict(body)

    def get_results(
        self,
        job_id: str,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[URLResult]:
        """Fetch one page of results. See ``iter_results()`` for streaming."""
        params = {"limit": int(limit), "offset": int(offset)}
        body = self._request("GET", f"/api/v2/jobs/{job_id}/results", params=params)
        items = body.get("items") or body.get("results") or []
        return [URLResult.from_dict(r) for r in items]

    def iter_results(
        self,
        job_id: str,
        *,
        page_size: int = 1000,
    ) -> Iterator[list[URLResult]]:
        """Stream all results for a job in pages.

        Yields lists of ``URLResult`` of at most ``page_size`` per
        iteration. Iteration ends when the server returns an empty or
        short page.
        """
        offset = 0
        while True:
            batch = self.get_results(job_id, limit=page_size, offset=offset)
            if not batch:
                return
            yield batch
            if len(batch) < page_size:
                return
            offset += page_size

    def wait_until_done(
        self,
        job_id: str,
        *,
        timeout: float = 900.0,
        poll_interval: float = 2.0,
    ) -> JobSummary:
        """Client-side poll loop. Returns when the job hits a terminal state.

        Convenience for the "I already submitted, just block until
        ready" case. Raises ``TimeoutError`` if the deadline passes.
        Terminal states are: completed, failed, cancelled, paused.
        """
        deadline = time.monotonic() + float(timeout)
        terminal = {"completed", "failed", "cancelled", "paused"}
        while True:
            job = self.get_job_status(job_id)
            if job.status in terminal:
                return job
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Job {job_id} did not finish within {timeout:.0f}s "
                    f"(last status: {job.status})"
                )
            time.sleep(poll_interval)

    # ---- Internals ----

    def _validate_urls(self, urls: Iterable[str]) -> list[str]:
        out: list[str] = []
        for u in urls:
            s = (u or "").strip()
            if not s:
                continue
            if not (s.lower().startswith("http://") or s.lower().startswith("https://")):
                raise ValidationError(
                    f"URLs must include a scheme (http:// or https://). Got: {u!r}"
                )
            out.append(s)
        if not out:
            raise ValidationError("No valid URLs provided.")
        return out

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.Timeout as e:
            raise TimeoutError(f"HTTP {method} {path} timed out after {self.timeout}s") from e
        except requests.RequestException as e:
            raise BulkURLCheckerError(
                f"Network error calling {method} {path}: {e}"
            ) from e

        return self._handle_response(resp)

    def _handle_response(self, resp: requests.Response) -> Any:
        request_id = resp.headers.get("X-Request-ID")
        if 200 <= resp.status_code < 300:
            try:
                return resp.json()
            except ValueError:
                return {}

        # Error path — try to extract the canonical {error: {code, message}}
        # envelope. Fall back to a generic message if the body isn't JSON.
        message = f"HTTP {resp.status_code} on {resp.request.method} {resp.url}"
        code: str | None = None
        details = None
        try:
            body = resp.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                code = err.get("code") or code
                message = err.get("message") or message
                details = err.get("details")
            else:
                # Some legacy endpoints still use `detail`
                d = body.get("detail") if isinstance(body, dict) else None
                if isinstance(d, str):
                    message = d
                elif isinstance(d, dict):
                    code = d.get("error") or code
                    message = d.get("message") or message
                    details = {k: v for k, v in d.items() if k not in ("error", "message")}
        except ValueError:
            pass

        status = resp.status_code
        if status in (401, 403) and code == "no_credits":
            raise QuotaError(
                message, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        if status in (401, 403):
            raise AuthenticationError(
                message, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        if status == 404:
            raise NotFoundError(
                message, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        if status == 429:
            retry_after = None
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    retry_after = int(float(ra))
                except (TypeError, ValueError):
                    retry_after = None
            raise RateLimitError(
                message, retry_after=retry_after, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        if status == 402:
            raise QuotaError(
                message, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        if status in (400, 422):
            raise ValidationError(
                message, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        if 500 <= status < 600:
            raise ServerError(
                message, status_code=status, code=code,
                request_id=request_id, details=details,
            )
        raise BulkURLCheckerError(
            message, status_code=status, code=code,
            request_id=request_id, details=details,
        )
