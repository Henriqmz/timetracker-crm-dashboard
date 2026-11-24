from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time


def generate_totp(secret_b32: str, timestamp: float | None = None, period: int = 30, digits: int = 6) -> str:
    """Generates an RFC 6238 TOTP code from a Base32 secret."""
    normalized = secret_b32.strip().replace(" ", "").upper()
    padded = normalized + "=" * (-len(normalized) % 8)
    key = base64.b32decode(padded)
    counter = int((timestamp if timestamp is not None else time.time()) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code_int).zfill(digits)


def verify_totp(
    secret_b32: str,
    code: str,
    timestamp: float | None = None,
    period: int = 30,
    valid_window: int = 1,
) -> bool:
    """Verifies a TOTP code allowing +/- valid_window time steps."""
    cleaned = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(cleaned) != 6:
        return False
    now = timestamp if timestamp is not None else time.time()
    for step in range(-valid_window, valid_window + 1):
        expected = generate_totp(secret_b32, timestamp=now + (step * period), period=period)
        if hmac.compare_digest(expected, cleaned):
            return True
    return False
