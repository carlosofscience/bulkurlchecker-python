"""Command-line interface for the Bulk URL Checker.

Install with the [cli] extra:

    pip install 'bulkurlchecker[cli]'

Then check a file of URLs (one per line) and emit a CSV:

    bulkurlchecker check urls.txt > report.csv

Or pipe in:

    cat urls.txt | bulkurlchecker check -

Set BULKURLCHECKER_API_KEY in the environment, or pass --api-key.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from typing import IO, Iterable

import click

from . import Client, __version__
from .exceptions import (
    AuthenticationError,
    BulkURLCheckerError,
    QuotaError,
    RateLimitError,
)


def _read_urls(source: IO[str]) -> list[str]:
    """Read URLs one per line from a file or stdin. Skips empty lines and
    a leading 'url'/'urls'/'link' header if it's the very first row."""
    urls: list[str] = []
    for i, raw in enumerate(source):
        s = raw.strip()
        if not s:
            continue
        if i == 0 and s.lower() in {"url", "urls", "link"}:
            continue
        urls.append(s)
    return urls


def _resolve_api_key(flag_value: str | None) -> str:
    key = flag_value or os.environ.get("BULKURLCHECKER_API_KEY")
    if not key:
        raise click.ClickException(
            "API key required. Pass --api-key or set BULKURLCHECKER_API_KEY. "
            "Get a key at https://app.bulkurlchecker.com/dashboard/api-keys"
        )
    return key


def _emit_csv(results: Iterable, out: IO[str]) -> None:
    writer = csv.writer(out)
    writer.writerow([
        "url", "status_code", "final_url", "is_broken",
        "is_soft_404", "redirect_hops", "response_time_ms",
    ])
    for r in results:
        writer.writerow([
            r.url,
            r.status_code if r.status_code is not None else "",
            r.final_url or "",
            "yes" if r.is_broken else "no",
            "yes" if r.is_soft_404 else "no",
            len(r.redirect_chain),
            r.response_time_ms if r.response_time_ms is not None else "",
        ])


def _emit_json(results: Iterable, out: IO[str]) -> None:
    rows = [
        {
            "url": r.url,
            "status_code": r.status_code,
            "final_url": r.final_url,
            "is_broken": r.is_broken,
            "is_soft_404": r.is_soft_404,
            "redirect_chain": r.redirect_chain,
            "response_time_ms": r.response_time_ms,
        }
        for r in results
    ]
    json.dump(rows, out, indent=2)
    out.write("\n")


def _emit_jsonl(results: Iterable, out: IO[str]) -> None:
    for r in results:
        json.dump(
            {
                "url": r.url,
                "status_code": r.status_code,
                "final_url": r.final_url,
                "is_broken": r.is_broken,
                "is_soft_404": r.is_soft_404,
                "redirect_chain": r.redirect_chain,
                "response_time_ms": r.response_time_ms,
            },
            out,
            separators=(",", ":"),
        )
        out.write("\n")


EMITTERS = {"csv": _emit_csv, "json": _emit_json, "jsonl": _emit_jsonl}


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="bulkurlchecker")
def cli() -> None:
    """Bulk URL Checker CLI — check thousands of URLs from the terminal."""


@cli.command()
@click.argument("source", type=click.File("r"), required=False)
@click.option(
    "--urls", "-u", "inline",
    help="Comma-separated URLs (alternative to passing a file/stdin).",
)
@click.option(
    "--api-key", "api_key", envvar="BULKURLCHECKER_API_KEY",
    help="API key. Also reads BULKURLCHECKER_API_KEY from env.",
)
@click.option(
    "--output", "-o", "output_format",
    type=click.Choice(["csv", "json", "jsonl"]),
    default="csv",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--wait", "wait_seconds",
    type=int, default=120, show_default=True,
    help="Max seconds to wait server-side for completion (1-900).",
)
@click.option(
    "--only-broken", is_flag=True,
    help="Emit only URLs the engine flagged as broken.",
)
@click.option(
    "--quiet", "-q", is_flag=True,
    help="Suppress the progress line on stderr.",
)
def check(
    source: IO[str] | None,
    inline: str | None,
    api_key: str | None,
    output_format: str,
    wait_seconds: int,
    only_broken: bool,
    quiet: bool,
) -> None:
    """Submit URLs and write results to stdout.

    Supply URLs as a file argument, via stdin (`-`), or with --urls.
    """
    if inline and source:
        raise click.UsageError("Pass URLs via --urls OR a file/stdin, not both.")
    if not inline and source is None:
        raise click.UsageError("No URL source. Pass a file path, '-' for stdin, or --urls.")

    if inline:
        urls = [u.strip() for u in inline.split(",") if u.strip()]
    else:
        assert source is not None
        urls = _read_urls(source)

    if not urls:
        raise click.UsageError("No URLs found in input.")

    key = _resolve_api_key(api_key)
    client = Client(api_key=key)

    if not quiet:
        click.echo(
            f"Submitting {len(urls):,} URL{'s' if len(urls) != 1 else ''} "
            f"(wait up to {wait_seconds}s)...",
            err=True,
        )

    try:
        out = client.check_urls(urls, wait_seconds=wait_seconds)
    except QuotaError as e:
        raise click.ClickException(
            f"Out of credits ({e}). Top up at https://app.bulkurlchecker.com/billing"
        ) from e
    except RateLimitError as e:
        raise click.ClickException(
            f"Rate limited. Retry after {e.retry_after}s." if e.retry_after
            else "Rate limited. Retry shortly."
        ) from e
    except AuthenticationError as e:
        raise click.ClickException(f"API key rejected: {e}") from e
    except BulkURLCheckerError as e:
        raise click.ClickException(
            f"{e}" + (f" (request_id={e.request_id})" if getattr(e, "request_id", None) else "")
        ) from e

    if not quiet:
        click.echo(
            f"Finished: status={out.status}, "
            f"completed={out.completed_urls:,}/{out.total_urls:,}, "
            f"broken={len(out.broken):,}"
            + (" (server-side wait timed out; partial results)" if out.timed_out else ""),
            err=True,
        )

    rows = out.broken if only_broken else out.results
    EMITTERS[output_format](rows, sys.stdout)


@cli.command()
@click.argument("source", type=click.File("r"), required=False)
@click.option("--urls", "-u", "inline", help="Comma-separated URLs.")
@click.option("--api-key", envvar="BULKURLCHECKER_API_KEY")
def submit(source: IO[str] | None, inline: str | None, api_key: str | None) -> None:
    """Submit URLs and print the job id. Doesn't wait for completion."""
    if inline and source:
        raise click.UsageError("Pass URLs via --urls OR a file/stdin, not both.")
    if not inline and source is None:
        raise click.UsageError("No URL source. Pass a file, '-' for stdin, or --urls.")
    urls = (
        [u.strip() for u in inline.split(",") if u.strip()]
        if inline else _read_urls(source)  # type: ignore[arg-type]
    )
    if not urls:
        raise click.UsageError("No URLs found in input.")
    key = _resolve_api_key(api_key)
    job = Client(api_key=key).submit(urls)
    click.echo(job.job_id)


@cli.command()
@click.argument("job_id")
@click.option("--api-key", envvar="BULKURLCHECKER_API_KEY")
def status(job_id: str, api_key: str | None) -> None:
    """Print the current status of a job."""
    key = _resolve_api_key(api_key)
    job = Client(api_key=key).get_job_status(job_id)
    click.echo(
        f"{job.job_id}\t{job.status}\t"
        f"{job.completed_urls}/{job.total_urls}"
    )


@cli.command()
@click.argument("job_id")
@click.option(
    "--output", "-o", "output_format",
    type=click.Choice(["csv", "json", "jsonl"]),
    default="csv", show_default=True,
)
@click.option("--api-key", envvar="BULKURLCHECKER_API_KEY")
def results(job_id: str, output_format: str, api_key: str | None) -> None:
    """Fetch full results for a completed job and write to stdout."""
    key = _resolve_api_key(api_key)
    client = Client(api_key=key)
    all_rows = []
    for batch in client.iter_results(job_id, page_size=1000):
        all_rows.extend(batch)
    EMITTERS[output_format](all_rows, sys.stdout)


if __name__ == "__main__":
    cli()
