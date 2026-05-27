"""Minimal example: check a small list of URLs and print broken ones.

Run with:
    export BULKURLCHECKER_API_KEY=uck_live_...
    python examples/basic_check.py
"""

import os
import sys

from bulkurlchecker import Client


def main() -> int:
    api_key = os.environ.get("BULKURLCHECKER_API_KEY")
    if not api_key:
        print("Set BULKURLCHECKER_API_KEY first. Get a key at "
              "https://app.bulkurlchecker.com/dashboard/api-keys")
        return 1

    client = Client(api_key=api_key)

    urls = [
        "https://example.com",
        "https://example.org",
        "https://example.com/nonexistent-page-for-demo",
    ]

    print(f"Submitting {len(urls)} URLs...")
    results = client.check_urls(urls, wait_seconds=60)

    print(f"\nFinished: status={results.status}, "
          f"completed={results.completed_urls}/{results.total_urls}")
    print(f"Broken: {len(results.broken)}\n")

    for r in results.results:
        marker = "BROKEN" if r.is_broken else "  ok  "
        print(f"  [{marker}] {r.status_code or '?':>3} {r.url}")

    if results.broken:
        print(f"\n{len(results.broken)} URL(s) need attention.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
