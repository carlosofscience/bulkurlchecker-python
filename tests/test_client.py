"""Unit tests for the Bulk URL Checker SDK.

Run:
    pip install -e .[dev]
    pytest tests/
"""

import pytest
import responses

from bulkurlchecker import (
    AuthenticationError,
    Client,
    NotFoundError,
    QuotaError,
    RateLimitError,
    ServerError,
    ValidationError,
)


API = "https://api.bulkurlchecker.com"


@pytest.fixture
def client():
    return Client(api_key="uck_test_fake")


def test_init_requires_api_key():
    with pytest.raises(AuthenticationError):
        Client(api_key="")


def test_validates_urls_have_scheme(client):
    with pytest.raises(ValidationError):
        client._validate_urls(["example.com"])  # no scheme


def test_validates_at_least_one_url(client):
    with pytest.raises(ValidationError):
        client._validate_urls([""])  # all empty


def test_strips_whitespace(client):
    assert client._validate_urls(["  https://example.com  "]) == ["https://example.com"]


@responses.activate
def test_check_urls_happy_path(client):
    responses.post(
        f"{API}/api/v2/jobs/wait",
        json={
            "job_id": "abc-123",
            "status": "completed",
            "timed_out": False,
            "total_urls": 2,
            "completed_urls": 2,
            "duplicates_removed": 0,
            "invalid_urls_rejected": 0,
            "completed_at": "2026-05-26T00:00:00Z",
            "results": [
                {"url": "https://example.com", "status_code": 200, "is_broken": False},
                {"url": "https://example.org", "status_code": 404, "is_broken": True},
            ],
        },
        status=200,
    )

    out = client.check_urls(["https://example.com", "https://example.org"])
    assert out.is_complete
    assert out.total_urls == 2
    assert len(out.results) == 2
    assert len(out.broken) == 1
    assert out.broken[0].url == "https://example.org"


@responses.activate
def test_submit_returns_job_summary(client):
    responses.post(
        f"{API}/api/v2/jobs",
        json={
            "job_id": "job-xyz",
            "status": "parsing",
            "total_urls": 5,
            "credits_allocated": 5,
            "duplicates_removed": 0,
            "invalid_urls_rejected": 0,
        },
        status=201,
    )
    job = client.submit(["https://example.com"] * 5)
    assert job.job_id == "job-xyz"
    assert job.status == "parsing"
    assert job.total_urls == 5


@responses.activate
def test_iter_results_paginates(client):
    # First page: 1000 items
    responses.get(
        f"{API}/api/v2/jobs/job-xyz/results",
        json={"items": [{"url": f"https://e/{i}", "status_code": 200} for i in range(1000)]},
        status=200,
    )
    # Second page: 200 items (less than page_size => stop)
    responses.get(
        f"{API}/api/v2/jobs/job-xyz/results",
        json={"items": [{"url": f"https://e/{i}", "status_code": 200} for i in range(1000, 1200)]},
        status=200,
    )

    batches = list(client.iter_results("job-xyz", page_size=1000))
    assert len(batches) == 2
    assert sum(len(b) for b in batches) == 1200


@responses.activate
def test_401_raises_authentication_error(client):
    responses.post(
        f"{API}/api/v2/jobs/wait",
        json={"error": {"code": "unauthorized", "message": "bad key"}},
        status=401,
    )
    with pytest.raises(AuthenticationError):
        client.check_urls(["https://example.com"])


@responses.activate
def test_429_raises_rate_limit_with_retry_after(client):
    responses.post(
        f"{API}/api/v2/jobs/wait",
        json={"error": {"code": "rate_limited", "message": "slow down"}},
        status=429,
        headers={"Retry-After": "60"},
    )
    with pytest.raises(RateLimitError) as exc_info:
        client.check_urls(["https://example.com"])
    assert exc_info.value.retry_after == 60


@responses.activate
def test_402_raises_quota_error(client):
    responses.post(
        f"{API}/api/v2/jobs/wait",
        json={"error": {"code": "no_credits", "message": "out of credits"}},
        status=402,
    )
    with pytest.raises(QuotaError):
        client.check_urls(["https://example.com"])


@responses.activate
def test_404_raises_not_found(client):
    responses.get(
        f"{API}/api/v2/jobs/missing",
        json={"error": {"code": "not_found", "message": "no such job"}},
        status=404,
    )
    with pytest.raises(NotFoundError):
        client.get_job_status("missing")


@responses.activate
def test_500_raises_server_error(client):
    responses.post(
        f"{API}/api/v2/jobs/wait",
        json={"error": {"code": "internal_error", "message": "boom"}},
        status=500,
    )
    with pytest.raises(ServerError):
        client.check_urls(["https://example.com"])


@responses.activate
def test_request_id_propagates_to_exception(client):
    responses.post(
        f"{API}/api/v2/jobs/wait",
        json={"error": {"code": "internal_error", "message": "boom"}},
        status=500,
        headers={"X-Request-ID": "req-abc"},
    )
    with pytest.raises(ServerError) as exc_info:
        client.check_urls(["https://example.com"])
    assert exc_info.value.request_id == "req-abc"


def test_user_agent_includes_sdk_marker(client):
    ua = client._session.headers["User-Agent"]
    assert ua.startswith("bulkurlchecker-python/")
