"""Compact feasibility source fingerprints for DynamoDB project-state size.

Legacy FE builds embedded full section HTML + fields in
``feasibility_document.source_fingerprint``, which could push a single
DynamoDB item over the 400 KB cap. Matches the FE ``cyrb53`` compact form
``{key, bodyHash, status}``.
"""

from __future__ import annotations

import json
from typing import Any


def _imul(a: int, b: int) -> int:
    """JS Math.imul — 32-bit signed multiply, result as unsigned 32-bit."""
    a &= 0xFFFFFFFF
    b &= 0xFFFFFFFF
    ah = (a >> 16) & 0xFFFF
    al = a & 0xFFFF
    bh = (b >> 16) & 0xFFFF
    bl = b & 0xFFFF
    return (al * bl + (((ah * bl + al * bh) & 0xFFFF) << 16)) & 0xFFFFFFFF


def hash_section_body(body: str) -> str:
    """cyrb53 — same algorithm as civil-ai-fe ``hashSectionBody``."""
    h1 = 0xDEADBEEF
    h2 = 0x41C6CE57
    for ch in body:
        c = ord(ch)
        h1 = _imul(h1 ^ c, 2654435761)
        h2 = _imul(h2 ^ c, 1597334677)
    h1 = (_imul(h1 ^ (h1 >> 16), 2246822507) ^ _imul(h2 ^ (h2 >> 13), 3266489909)) & 0xFFFFFFFF
    h2 = (_imul(h2 ^ (h2 >> 16), 2246822507) ^ _imul(h1 ^ (h1 >> 13), 3266489909)) & 0xFFFFFFFF
    return f"{h2:08x}{h1:08x}"


def _body_token(entry: dict[str, Any]) -> str:
    body_hash = entry.get("bodyHash")
    if isinstance(body_hash, str) and body_hash.strip():
        return body_hash
    body = entry.get("body")
    return hash_section_body(body if isinstance(body, str) else "")


def compact_feasibility_fingerprint(source_fingerprint: str | None) -> str | None:
    """Rewrite a stored fingerprint to the compact form, or return unchanged."""
    if source_fingerprint is None:
        return None
    if not source_fingerprint.strip():
        return source_fingerprint
    try:
        parsed: Any = json.loads(source_fingerprint)
    except json.JSONDecodeError:
        return source_fingerprint
    if not isinstance(parsed, list):
        return source_fingerprint
    compact: list[dict[str, str]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            continue
        status = entry.get("status")
        compact.append(
            {
                "key": key,
                "bodyHash": _body_token(entry),
                "status": status if isinstance(status, str) and status else "draft",
            }
        )
    return json.dumps(compact, separators=(",", ":"))
