"""JSONL framing for pi's RPC mode.

Records are split on LF only. U+2028/U+2029 are legal inside JSON strings, so text-mode
readline and `str.splitlines` are wrong; a binary stream splits on b"\\n" alone.
"""

from __future__ import annotations

import msgspec


def encode_record(record: dict) -> bytes:
    return msgspec.json.encode(record) + b"\n"


def iter_records(stream):
    """Yield decoded records from a binary stream until EOF."""
    for raw in stream:
        line = raw.rstrip(b"\r\n")
        if not line.strip():
            continue
        try:
            yield msgspec.json.decode(line)
        except msgspec.DecodeError as exc:
            raise ValueError(f"bad protocol record: {exc}") from exc
