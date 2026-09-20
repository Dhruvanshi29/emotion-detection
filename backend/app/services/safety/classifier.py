"""Rule-based safety classifier.

Kept intentionally separate from the LLM path (plan §13: "Separate safety
classification from ordinary response generation so safety logic cannot be
skipped by the conversational model"). This is heuristic-only for MVP; a
learned classifier can slot in behind the same `classify()` signature later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

Level = str  # "none" | "low" | "medium" | "high"


@dataclass
class RiskResult:
    level: Level
    categories: List[str] = field(default_factory=list)
    rationale: str = ""


_HIGH_PATTERNS = [
    (r"\b(?:kill|end|hurt|harm)\s+(?:myself|me)\b", "self_harm"),
    (r"\bend\s+my\s+life\b", "self_harm"),
    (r"\bsuicid(?:e|al)\b", "self_harm"),
    (r"\bwant(?:ed)?\s+to\s+die\b", "self_harm"),
    (r"\bdon['\u2019]?t\s+want\s+to\s+(?:be|live)\b", "self_harm"),
    (r"\bno\s+reason\s+to\s+live\b", "self_harm"),
    (r"\btake\s+my\s+(?:own\s+)?life\b", "self_harm"),
    (r"\boverdose\b|\bod\s+on\b", "self_harm"),
    (r"\bkill\s+(?:him|her|them|someone|people)\b", "harm_others"),
    (r"\b(?:being|is|are)\s+abus(?:ed|ing)\b", "abuse"),
    (r"\bhe\s+hits\s+me\b|\bshe\s+hits\s+me\b|\bthey\s+hit\s+me\b", "abuse"),
]

_MEDIUM_PATTERNS = [
    (r"\bself[-\s]?harm(?:ing|ed|s)?\b", "self_harm"),
    (r"\bcut(?:ting)?\s+myself\b", "self_harm"),
    (r"\bhopeless\b|\bworthless\b", "distress"),
    (r"\bcan['\u2019]?t\s+go\s+on\b", "distress"),
    (r"\bpanic\s+attack\b", "distress"),
]

_LOW_PATTERNS = [
    (r"\bdepress(?:ed|ion)\b", "low_mood"),
    (r"\banxious\b|\banxiety\b", "anxiety"),
    (r"\blonely\b|\bisolat(?:ed|ing)\b", "isolation"),
    (r"\bcry(?:ing)?\b|\bcried\b", "distress"),
    (r"\bstress(?:ed)?\b|\boverwhelmed\b", "stress"),
]


def _match_any(text: str, patterns) -> List[str]:
    hits: List[str] = []
    for pat, cat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            hits.append(cat)
    # de-dup preserving order
    seen = set()
    out = []
    for c in hits:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def classify(text: str) -> RiskResult:
    """Return the risk level for a single user turn."""
    if not text or not text.strip():
        return RiskResult("none")

    high = _match_any(text, _HIGH_PATTERNS)
    if high:
        return RiskResult("high", high, "matched high-risk pattern")

    med = _match_any(text, _MEDIUM_PATTERNS)
    if med:
        return RiskResult("medium", med, "matched medium-risk pattern")

    low = _match_any(text, _LOW_PATTERNS)
    if low:
        return RiskResult("low", low, "matched low-risk pattern")

    return RiskResult("none")
