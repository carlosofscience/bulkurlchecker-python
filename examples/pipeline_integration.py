"""Pipeline example: bulk-check a list of URLs from a CSV and write
results back as a new CSV. Demonstrates the streaming results pattern
appropriate for >10K URL jobs.

Run with:
    export BULKURLCHECKER_API_KEY=uck_live_...
    python examples/pipeline_integration.py input_urls.csv output_results.csv
"""

import csv
import os
import sys

from bulkurlchecker import (
    Client,
    QuotaError,
    RateLimitError,
)


def load_urls_from_csv(path: str) -> list[str]:
    """Read URLs from the first column of a CSV (header optional)."""
    out: list[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row:
                continue
            cell = row[0].strip()
            # Skip the header row if column 0 is literally "url"
            if i == 0 and cell.lower() in {"url", "urls", "link"}:
                continue
            if cell:
                out.append(cell)
    return out


def main() -> int:
    api_key = os.environ.get("BULKURLCHECKER_API_KEY")
    if not api_key:
        print("Set BULKURLCHECKER_API_KEY first.")
        return 1

    if len(sys.argv) < 3:
        print("Usage: python pipeline_integration.py <input.csv> <output.csv>")
        return 1
    in_path, out_path = sys.argv[1], sys.argv[2]

    urls = load_urls_from_csv(in_path)
    print(f"Loaded {len(urls):,} URLs from {in_path}")

    client = Client(api_key=api_key)

    # Submit and let the engine work in the background while we set up
    # the output writer.
    try:
        job = client.submit(urls)
    except QuotaError:
        print("Out of credits. Top up at https://app.bulkurlchecker.com/billing")
        return 2
    except RateLimitError as e:
        print(f"Rate limited. Retry after {e.retry_after}s.")
        return 2

    print(f"Submitted job {job.job_id} ({job.total_urls:,} URLs, "
          f"{job.duplicates_removed} dupes removed)")

    # Block until the engine finishes. For very large jobs, raise the
    # timeout — wait_until_done() polls every 2s and returns as soon
    # as the job hits a terminal state.
    print("Waiting for completion...")
    final = client.wait_until_done(job.job_id, timeout=3600)
    print(f"Done. status={final.status}, completed_urls={final.completed_urls:,}")

    # Stream results to disk in pages. iter_results yields lists of
    # URLResult; one row per URL in the output CSV.
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "status_code", "final_url", "is_broken", "is_soft_404", "redirect_hops"])
        rows_written = 0
        for batch in client.iter_results(job.job_id, page_size=1000):
            for r in batch:
                writer.writerow([
                    r.url,
                    r.status_code or "",
                    r.final_url or "",
                    "yes" if r.is_broken else "no",
                    "yes" if r.is_soft_404 else "no",
                    len(r.redirect_chain),
                ])
                rows_written += 1
            print(f"  Wrote {rows_written:,} rows so far...")

    print(f"\nWrote {rows_written:,} rows to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
