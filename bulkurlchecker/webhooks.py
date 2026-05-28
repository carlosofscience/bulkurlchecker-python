"""
Webhook signature verification for incoming POSTs from Bulk URL Checker.

When a job finishes, our server POSTs to your registered endpoint with
a header like::

    Bulkurlchecker-Signature: t=1779938676,v1=498569f1729...

Use ``verify_signature()`` in your handler to reject anyone who isn't
us. Skipping this check means anyone who knows your endpoint URL can
fake completion events. Don't skip it.

Minimal example with Flask::

    from bulkurlchecker.webhooks import verify_signature, InvalidSignatureError

    SECRET = os.environ["MY_WEBHOOK_SECRET"]  # the signing_secret we showed once

    @app.route("/webhook/bulkurlchecker", methods=["POST"])
    def hook():
        try:
            verify_signature(
                request.get_data(),  # RAW bytes; not json
                request.headers.get("Bulkurlchecker-Signature", ""),
                SECRET,
            )
        except InvalidSignatureError:
            return "", 401
        event = request.get_json()
        # ... handle event ...
        return "", 200

Tolerance defaults to 300 seconds. Beyond that the signature is rejected
even if cryptographically valid, to defeat replay attacks with the same
captured payload.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable

from .exceptions import BulkURLCheckerError

__all__ = [
    "verify_signature",
    "InvalidSignatureError",
    "DEFAULT_TOLERANCE_SECONDS",
]


DEFAULT_TOLERANCE_SECONDS = 300  # 5 minutes; matches Stripe convention


class InvalidSignatureError(BulkURLCheckerError):
    """Raised when the Bulkurlchecker-Signature header is missing,
    malformed, expired, or doesn't match the secret."""


def _parse_signature_header(header: str) -> tuple[int, str]:
    """Pull (timestamp, v1_hex) out of `t=...,v1=...` format. Raises on bad input."""
    if not header:
        raise InvalidSignatureError("Missing Bulkurlchecker-Signature header")
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
    except ValueError as e:
        raise InvalidSignatureError(f"Malformed signature header: {e}") from e
    ts_raw = parts.get("t")
    v1 = parts.get("v1")
    if ts_raw is None or v1 is None:
        raise InvalidSignatureError(
            "Signature header missing required 't' and/or 'v1' fields"
        )
    try:
        ts = int(ts_raw)
    except ValueError as e:
        raise InvalidSignatureError(f"Non-integer timestamp: {ts_raw!r}") from e
    return ts, v1


def verify_signature(
    raw_body: bytes,
    header: str,
    secret: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now_fn: Callable[[], float] | None = None,
) -> None:
    """
    Verify the Bulkurlchecker-Signature header.

    Raises:
        InvalidSignatureError: signature missing, malformed, expired,
        or doesn't match.

    Args:
        raw_body: The HTTP request body as bytes (NOT parsed JSON --
            re-encoding changes whitespace and breaks the signature).
        header: The full value of the Bulkurlchecker-Signature header.
        secret: Your endpoint's signing_secret (the value returned once
            at endpoint-creation time).
        tolerance_seconds: Reject signatures older than this many
            seconds even if cryptographically valid. Defaults to 300.
            Pass 0 to disable the timestamp check (don't, in production).
        now_fn: Override of `time.time` for tests. Don't touch in prod.

    Returns None on success. Use try/except to branch.
    """
    if not isinstance(raw_body, (bytes, bytearray)):
        raise InvalidSignatureError(
            "raw_body must be bytes. Use request.get_data() / request.body "
            "(not the parsed JSON object)."
        )
    if not secret:
        raise InvalidSignatureError("secret must be non-empty")

    ts, v1 = _parse_signature_header(header)

    if tolerance_seconds > 0:
        now = int((now_fn or time.time)())
        if abs(now - ts) > tolerance_seconds:
            raise InvalidSignatureError(
                f"Signature timestamp outside tolerance window of "
                f"{tolerance_seconds}s (received {ts}, now {now}). "
                "Replay attempt or clock skew."
            )

    signed_payload = f"{ts}.{raw_body.decode('utf-8')}".encode()
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, v1):
        raise InvalidSignatureError(
            "Signature does not match. Body may have been tampered with, "
            "or the wrong secret was supplied."
        )
