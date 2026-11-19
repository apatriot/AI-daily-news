"""Content filters: AI relevance and promotional noise."""
from __future__ import annotations


def matches_any(text: str, patterns: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(str(p).lower() in lowered for p in patterns if str(p).strip())


def is_noise(title: str, summary: str, patterns: list[str]) -> bool:
    """Event sign-ups, ads and recruitment posts are not news."""
    return matches_any(f"{title} {summary}", patterns)


def is_ai_related(title: str, summary: str, keywords: list[str]) -> bool:
    return matches_any(f"{title} {summary}", keywords)
