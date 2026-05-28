# Changelog

All notable changes to this project will be documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/) once
it reaches 1.0. While we're at 0.x, breaking changes may land in minor
releases; they'll always be noted under "Changed" or "Removed."

## [Unreleased]

## [0.5.0] - 2026-05-28

### Added
- `bulkurlchecker.verify_signature(raw_body, header, secret)` for
  verifying incoming `Bulkurlchecker-Signature` headers on webhook
  receivers. Raises `InvalidSignatureError` on missing/malformed/
  expired/tampered signatures.
- `InvalidSignatureError` exception (subclass of `BulkURLCheckerError`).
- 5-minute default replay-attack tolerance window. Override via
  `tolerance_seconds=`.

## [0.4.0] - 2026-05-28

### Added
- `cursor` parameter on `client.get_results()` and a new
  `client.get_results_page()` that returns `(results, next_cursor)`.
  Cursor pagination is stable under concurrent writes — page contents
  don't shift if a slow-checking URL finishes mid-export.
- `client.iter_results()` now uses cursor pagination under the hood for
  the same stability benefit. No API change for callers.

### Changed
- The internal pagination strategy for `iter_results()` shifted from
  offset-based to cursor-based. Behavior is identical for normal
  callers; if you were relying on the precise request sequence the
  iterator emits (e.g., via a mocked transport), the second and later
  requests now include a `cursor=` query param instead of an `offset=`.

## [0.3.0] - 2026-05-28

### Added
- `idempotency_key` parameter on `client.submit()` and
  `client.check_urls()`. Pass a UUIDv4 (or any unique string) to make
  retries safe. Same key + same body within 24h returns the original
  response without creating a duplicate job. Same key + different
  body returns `ValidationError`. Sent as the `Idempotency-Key` header
  per the IETF draft / Stripe convention.

### Changed
- Dropped support for Python 3.8 and 3.9 (both EOL: October 2024 and
  October 2025 respectively). Minimum supported version is now Python
  3.10. Modern mypy no longer accepts 3.8/3.9 as type-check targets,
  and the CI lint/type-check tooling has dropped them as well. Added
  Python 3.13 to the CI matrix.

## [0.2.0] - 2026-05-27

### Added
- Command-line interface. Install with `pip install 'bulkurlchecker[cli]'`,
  then `bulkurlchecker check urls.txt > report.csv`. Subcommands:
  - `check` — submit + wait + emit results to stdout (csv/json/jsonl).
  - `submit` — submit and print the job id (no wait).
  - `status` — print the current state of a job.
  - `results` — fetch and emit results for a finished job.
- `--only-broken` flag on `check` to filter to broken URLs only.
- Reads `BULKURLCHECKER_API_KEY` from the environment, or `--api-key`.

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
