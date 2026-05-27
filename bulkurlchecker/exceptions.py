"""Exception hierarchy for the Bulk URL Checker SDK.

All errors derive from BulkURLCheckerError so callers can catch a
single exception type and branch on it. Specific subclasses exist
for the error categories devs actually want to handle differently:
authentication, rate limiting, quota, and validation.
"""

from __future__ import annotations

from typing import Any, Optional


class BulkURLCheckerError(Exception):
    """Base class for all SDK errors.

    Carries the HTTP status code, the server's machine-readable
    `error.code`, and the request_id so support requests are easy to
    triage. Always raise the most-specific subclass possible.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.details = details

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        parts = [self.__class__.__name__, repr(str(self))]
        if self.status_code is not None:
            parts.append(f"status_code={self.status_code}")
        if self.code:
            parts.append(f"code={self.code!r}")
        if self.request_id:
            parts.append(f"request_id={self.request_id!r}")
        return f"<{' '.join(parts)}>"


class AuthenticationError(BulkURLCheckerError):
    """401 / 403. The API key is missing, invalid, or revoked."""


class RateLimitError(BulkURLCheckerError):
    """429. Slow down. Inspect `retry_after` (seconds) if present."""

    def __init__(self, *args: Any, retry_after: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class QuotaError(BulkURLCheckerError):
    """402 / 403 when the user has run out of credits or hit a plan limit."""


class ValidationError(BulkURLCheckerError):
    """400 / 422. The request was malformed (bad URLs, too many URLs, etc)."""


class NotFoundError(BulkURLCheckerError):
    """404. The job ID isn't owned by this API key, or doesn't exist."""


class ServerError(BulkURLCheckerError):
    """5xx. Transient issue on our side; safe to retry with backoff."""


class TimeoutError(BulkURLCheckerError):  # noqa: A001 - intentional shadow
    """The local request timeout elapsed before the server responded."""
