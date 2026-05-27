"""Public response types for the Bulk URL Checker SDK.

These are intentionally simple dataclasses (not pydantic models) so the
SDK has zero runtime dependencies beyond `requests`. If you want full
type validation, the OpenAPI spec lives at
https://api.bulkurlchecker.com/openapi.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobSummary:
    """High-level state of a single URL-checking job."""

    job_id: str
    status: str  # 'pending' | 'parsing' | 'processing' | 'paused' | 'completed' | 'failed' | 'cancelled'
    total_urls: int
    completed_urls: int = 0
    credits_allocated: int = 0
    duplicates_removed: int = 0
    invalid_urls_rejected: int = 0
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> JobSummary:
        return cls(
            job_id=str(d.get("job_id") or d.get("id")),
            status=str(d.get("status") or "pending"),
            total_urls=int(d.get("total_urls") or 0),
            completed_urls=int(d.get("completed_urls") or 0),
            credits_allocated=int(d.get("credits_allocated") or 0),
            duplicates_removed=int(d.get("duplicates_removed") or 0),
            invalid_urls_rejected=int(d.get("invalid_urls_rejected") or 0),
            created_at=d.get("created_at"),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
        )


@dataclass
class URLResult:
    """One URL check result. Shape mirrors the API response."""

    url: str
    final_url: str | None = None
    status_code: int | None = None
    response_time_ms: int | None = None
    redirect_chain: list[str] = field(default_factory=list)
    is_broken: bool = False
    is_soft_404: bool = False
    error_code: str | None = None
    content_type: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> URLResult:
        # The API returns slightly different field names depending on
        # the endpoint version; this normalizer keeps the SDK shape
        # stable across server-side changes.
        return cls(
            url=str(d.get("url") or ""),
            final_url=d.get("final_url") or d.get("final"),
            status_code=d.get("status_code") or d.get("status"),
            response_time_ms=d.get("response_time_ms") or d.get("duration_ms"),
            redirect_chain=list(d.get("redirect_chain") or []),
            is_broken=bool(d.get("is_broken") or False),
            is_soft_404=bool(d.get("is_soft_404") or False),
            error_code=d.get("error_code") or d.get("error"),
            content_type=d.get("content_type"),
        )


@dataclass
class CheckResults:
    """Complete result set from `Client.check_urls()` / `submit_and_wait()`."""

    job_id: str
    status: str
    timed_out: bool
    total_urls: int
    completed_urls: int
    duplicates_removed: int
    invalid_urls_rejected: int
    completed_at: str | None
    results: list[URLResult]

    @property
    def is_complete(self) -> bool:
        """True when the engine finished the job within the wait window."""
        return self.status == "completed" and not self.timed_out

    @property
    def broken(self) -> list[URLResult]:
        """All results where the engine marked the URL broken."""
        return [r for r in self.results if r.is_broken]

    @property
    def soft_404s(self) -> list[URLResult]:
        return [r for r in self.results if r.is_soft_404]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckResults:
        return cls(
            job_id=str(d.get("job_id") or ""),
            status=str(d.get("status") or ""),
            timed_out=bool(d.get("timed_out") or False),
            total_urls=int(d.get("total_urls") or 0),
            completed_urls=int(d.get("completed_urls") or 0),
            duplicates_removed=int(d.get("duplicates_removed") or 0),
            invalid_urls_rejected=int(d.get("invalid_urls_rejected") or 0),
            completed_at=d.get("completed_at"),
            results=[URLResult.from_dict(r) for r in (d.get("results") or [])],
        )
