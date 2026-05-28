"""Tests for bulkurlchecker.webhooks signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from bulkurlchecker.webhooks import (
    DEFAULT_TOLERANCE_SECONDS,
    InvalidSignatureError,
    verify_signature,
)

SECRET = "test-secret-do-not-use-in-prod-" + "a" * 32


def _make_header(secret: str, body: bytes, ts: int) -> str:
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.{body.decode('utf-8')}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={sig}"


def test_valid_signature_passes():
    body = json.dumps({"hello": "world"}, separators=(",", ":")).encode()
    ts = int(time.time())
    header = _make_header(SECRET, body, ts)
    verify_signature(body, header, SECRET)  # no raise = pass


def test_tampered_body_rejected():
    body = b'{"hello":"world"}'
    ts = int(time.time())
    header = _make_header(SECRET, body, ts)
    tampered = b'{"hello":"world!"}'
    with pytest.raises(InvalidSignatureError, match="does not match"):
        verify_signature(tampered, header, SECRET)


def test_wrong_secret_rejected():
    body = b'{"hello":"world"}'
    ts = int(time.time())
    header = _make_header(SECRET, body, ts)
    with pytest.raises(InvalidSignatureError, match="does not match"):
        verify_signature(body, header, "wrong-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx")


def test_missing_header_rejected():
    with pytest.raises(InvalidSignatureError, match="Missing"):
        verify_signature(b'{}', "", SECRET)


def test_malformed_header_rejected():
    # 'garbage' has no '=' so the split fails, raising 'Malformed'.
    with pytest.raises(InvalidSignatureError, match="Malformed signature header"):
        verify_signature(b'{}', "garbage", SECRET)
    # Missing required field surfaces the 'missing required' message.
    with pytest.raises(InvalidSignatureError, match="missing required"):
        verify_signature(b'{}', "t=1", SECRET)
    with pytest.raises(InvalidSignatureError, match="Non-integer timestamp"):
        verify_signature(b'{}', "t=abc,v1=def", SECRET)


def test_old_signature_rejected():
    body = b'{}'
    old_ts = int(time.time()) - DEFAULT_TOLERANCE_SECONDS - 60
    header = _make_header(SECRET, body, old_ts)
    with pytest.raises(InvalidSignatureError, match="outside tolerance"):
        verify_signature(body, header, SECRET)


def test_future_signature_rejected():
    body = b'{}'
    future_ts = int(time.time()) + DEFAULT_TOLERANCE_SECONDS + 60
    header = _make_header(SECRET, body, future_ts)
    with pytest.raises(InvalidSignatureError, match="outside tolerance"):
        verify_signature(body, header, SECRET)


def test_zero_tolerance_skips_timestamp_check():
    body = b'{}'
    very_old_ts = 1  # year 1970
    header = _make_header(SECRET, body, very_old_ts)
    # Should not raise even though timestamp is ancient
    verify_signature(body, header, SECRET, tolerance_seconds=0)


def test_str_body_rejected():
    with pytest.raises(InvalidSignatureError, match="must be bytes"):
        verify_signature("not bytes", "t=1,v1=x", SECRET)  # type: ignore[arg-type]


def test_empty_secret_rejected():
    with pytest.raises(InvalidSignatureError, match="non-empty"):
        verify_signature(b'{}', "t=1,v1=x", "")
