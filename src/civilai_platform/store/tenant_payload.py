from __future__ import annotations

from typing import Any

from civilai_platform.utils.slug import slugify, unique_slug


def collect_known_slugs(payloads: list[dict[str, Any]]) -> set[str]:
    return {str(slug) for payload in payloads if (slug := payload.get("url_slug"))}


def ensure_url_slug(
    payload: dict[str, Any],
    reserved_slugs: set[str],
) -> tuple[dict[str, Any], bool]:
    existing = payload.get("url_slug")
    if existing:
        reserved_slugs.add(str(existing))
        return payload, False
    slug = unique_slug(slugify(str(payload.get("name", "tenant"))), reserved_slugs)
    reserved_slugs.add(slug)
    return {**payload, "url_slug": slug}, True
