from __future__ import annotations

from typing import Any


def _text_blob(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(k, "") or "")
        for k in ("title", "abstract", "topics", "institutions")
    ).lower()


def _field_id(row: dict[str, Any]) -> str:
    return str(row.get("primary_field_id", "") or "")


def _topic_ids(row: dict[str, Any]) -> set[str]:
    raw = row.get("topic_ids", "")
    if isinstance(raw, list):
        return {str(t) for t in raw if t}
    return {t.strip() for t in str(raw).split(";") if t.strip()}


def is_excluded(row: dict[str, Any], filters: dict[str, Any]) -> tuple[bool, str]:
    """Return (excluded, reason). Unlisted topics pass through."""
    if str(row.get("discovery_source", "")).startswith("channel_g:"):
        return False, ""

    exclude = filters.get("exclude", {})
    text = _text_blob(row)
    topic_ids = _topic_ids(row)
    field_id = _field_id(row)

    medical = exclude.get("medical", {})
    if medical.get("enabled"):
        for fid in medical.get("openalex_fields", []):
            if field_id == str(fid.get("id", "")):
                return True, "medical_field"
        for kw in medical.get("keyword_title_abstract", []):
            if kw.lower() in text:
                return True, f"medical_keyword:{kw}"

    literary = exclude.get("literary_and_english_studies", {})
    if literary.get("enabled"):
        lit_topic_ids = {
            str(t.get("id", ""))
            for t in literary.get("openalex_topics", [])
            if t.get("id")
        }
        if topic_ids & lit_topic_ids:
            return True, "literary_topic"
        kw_hits = [
            kw
            for kw in literary.get("keyword_title_abstract", [])
            if kw.lower() in text
        ]
        if literary.get("require_any_keyword", True) and kw_hits:
            return True, f"literary_keyword:{kw_hits[0]}"

    return False, ""
