# Changelog

All notable changes to this project will be documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/) once
it reaches 1.0. While we're at 0.x, breaking changes may land in minor
releases; they'll always be noted under "Changed" or "Removed."

## [Unreleased]

## [0.1.0] - 2026-05-XX

Initial release.

### Added
- `Client(api_key=...)` synchronous client for the Bulk URL Checker REST API.
- `client.check_urls(urls)` — submit and block until results, in one call.
- `client.submit(urls)` — async submission returning a `JobSummary`.
- `client.get_job_status(job_id)` — current state of a previously-submitted job.
- `client.get_results(job_id, limit=, offset=)` — paginated results.
- `client.iter_results(job_id, page_size=)` — streaming generator.
- `client.wait_until_done(job_id, timeout=)` — client-side polling helper.
- Exception hierarchy under `BulkURLCheckerError`:
  `AuthenticationError`, `RateLimitError`, `QuotaError`, `ValidationError`,
  `NotFoundError`, `ServerError`, `TimeoutError`.
- Result types: `CheckResults`, `JobSummary`, `URLResult`.
- Type hints throughout (PEP 561 compliant; `py.typed` marker included).
- User-Agent set to `bulkurlchecker-python/<version>` so server-side
  channel telemetry can distinguish SDK traffic.
