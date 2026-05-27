"""bulkurlchecker — Python client for the Bulk URL Checker API.

Quickstart:

    from bulkurlchecker import Client
    client = Client(api_key="uck_live_...")
    results = client.check_urls([
        "https://example.com",
        "https://example.org",
    ])
    for r in results.results:
        print(r.url, r.status_code)

Get an API key at https://app.bulkurlchecker.com/dashboard/api-keys.
"""

from ._version import __version__
from .client import Client
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

__all__ = [
    "__version__",
    "Client",
    "CheckResults",
    "JobSummary",
    "URLResult",
    "BulkURLCheckerError",
    "AuthenticationError",
    "RateLimitError",
    "QuotaError",
    "ValidationError",
    "NotFoundError",
    "ServerError",
    "TimeoutError",
]
