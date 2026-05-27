# bulkurlchecker

[![PyPI version](https://img.shields.io/pypi/v/bulkurlchecker.svg)](https://pypi.org/project/bulkurlchecker/)
[![Python versions](https://img.shields.io/pypi/pyversions/bulkurlchecker.svg)](https://pypi.org/project/bulkurlchecker/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Python client for the [Bulk URL Checker](https://bulkurlchecker.com) API.

**Skip the proxy-rotation, rate-limiter, soft-404 detector, and retry classifier you would otherwise spend two weeks building.** Submit thousands of URLs, get status codes, redirect chains, and broken-link detection back as plain Python objects. Backed by a managed cloud service with residential proxies and per-domain throttling.

## Install

```bash
pip install bulkurlchecker
```

## 5-line example

```python
from bulkurlchecker import Client

client = Client(api_key="uck_live_...")
results = client.check_urls(["https://example.com", "https://example.org"])
for r in results.results:
    print(r.url, r.status_code, "BROKEN" if r.is_broken else "ok")
```

Get an API key at https://app.bulkurlchecker.com/dashboard/api-keys. First 300 URLs are free, no card required.

## What you get back

```python
results = client.check_urls(urls)

results.status            # 'completed' | 'paused' | 'failed' | 'cancelled'
results.timed_out         # True if the wait deadline passed (job still running)
results.total_urls        # how many URLs the engine accepted
results.completed_urls    # how many it finished checking
results.duplicates_removed
results.invalid_urls_rejected

for r in results.results:
    r.url                # the original URL you submitted
    r.final_url          # after redirects
    r.status_code        # 200, 301, 404, 429, 500, ...
    r.redirect_chain     # list of intermediate URLs
    r.is_broken          # True if the engine flagged this as broken
    r.is_soft_404        # True if 200 OK but page content says "not found"
    r.response_time_ms

# Convenience properties:
results.broken           # list of URLResult where is_broken == True
results.soft_404s        # list where is_soft_404 == True
```

## Larger jobs: submit and poll

`check_urls()` blocks for up to 15 minutes server-side. For lists where the wait would time out, use the two-step pattern:

```python
job = client.submit(my_500k_urls)
print(f"Submitted {job.job_id}, {job.total_urls} URLs queued")

# Poll explicitly, or use the convenience method
done = client.wait_until_done(job.job_id, timeout=3600)

# Stream results in pages
for batch in client.iter_results(job.job_id, page_size=1000):
    for r in batch:
        if r.is_broken:
            print(r.url, r.status_code)
```

## Error handling

All errors derive from `BulkURLCheckerError`. Catch specific subclasses when you want to branch on the failure mode:

```python
from bulkurlchecker import (
    Client,
    BulkURLCheckerError,
    AuthenticationError,
    RateLimitError,
    QuotaError,
    ValidationError,
)

try:
    results = client.check_urls(urls)
except QuotaError as e:
    print(f"Out of credits. Top up at https://app.bulkurlchecker.com/billing")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s.")
except AuthenticationError:
    print("API key rejected — check it's not revoked.")
except ValidationError as e:
    print(f"Bad request: {e}")  # bad URLs, too many URLs, etc.
except BulkURLCheckerError as e:
    print(f"Other error: {e} (request_id={e.request_id})")
```

Every error carries `status_code`, `code` (server's machine-readable string), `request_id` (for support), and `details` (when the server provides them).

## Why use this instead of writing your own checker with httpx + asyncio?

Honest answer: for ≤500 URLs you don't need this. The standard `requests`/`httpx` toolchain handles it fine.

The wall hits at scale:

| Problem | Rolling your own | This SDK |
|---|---|---|
| Concurrency | `asyncio` + careful semaphores | done |
| Proxy rotation across residential IPs | $90+/mo Webshare / Bright Data subscription + custom code | done |
| Per-domain rate limiting (so you don't hammer one host) | wire it yourself | done |
| Distinguishing real 403 from "you got blocked" 403 | guess and check | done |
| Detecting soft 404s (200 OK + "not found" body) | regex / heuristic per template | done |
| Retry classification (transient vs permanent) | tune for weeks | done |
| Long-running job state (resume after crash) | Redis + queue + worker infra | done |
| Engineer time, weeks 1-4 | $$$ | nothing, ship today |

If you've already lost a weekend to httpx + proxy rotation, you know what we're talking about.

## Pricing

- **Free tier:** 300 URL checks. No signup required.
- **Starter:** $9/month or $90/year (~17% off) — 15,000 URLs/month
- **Pro:** $29/month or $290/year — 50,000 URLs/month, 5 scheduled checks, daily monitoring
- **Agency:** $99/month or $990/year — 200,000 URLs/month, 50 schedules, Slack + webhook alerts

Top-up credit packs available beyond the monthly pool. Credits never expire.

Full pricing: https://bulkurlchecker.com/#pricing

## Links

- [Web app](https://app.bulkurlchecker.com)
- [REST API reference](https://bulkurlchecker.com/developers)
- [OpenAPI spec](https://api.bulkurlchecker.com/openapi.json)
- [GitHub](https://github.com/carlosofscience/bulkurlchecker-python)
- [Changelog](CHANGELOG.md)

## Stability

The SDK follows semver. While we're at 0.x, breaking changes can land in minor releases (we'll always note them in `CHANGELOG.md`). Once we hit 1.0 you can pin major versions safely.

## License

MIT. See [LICENSE](LICENSE).
