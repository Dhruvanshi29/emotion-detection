"""Prompt-injection and unsafe-output heuristics (plan §13, Phase 12).

Deliberately conservative: false positives here just add a safety flag,
they do NOT block the user's message. Downstream code decides how to react.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# Common injection markers seen in the wild. Each pattern is a category label.
_INJECTION_PATTERNS: List[tuple[str, str]] = [
    (r"ignore\s+(?:all|any|the)?\s*(?:previous|above|prior|earlier|prev)?\s*(?:instructions?|rules?|prompts?)", "instruction_override"),
    (r"disregard\s+(?:all|any|the)?\s*(?:previous|above|prior|earlier)?\s*(?:instructions?|rules?|prompts?)", "instruction_override"),
    (r"forget\s+(?:everything|all\s+(?:previous|prior|above|earlier)?\s*(?:instructions?|rules?)?)", "instruction_override"),
    (r"you\s+are\s+now\s+(?:a|an|dan|the)\s+", "role_override"),
    (r"act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:a|an)\s+", "role_override"),
    (r"pretend\s+(?:to\s+be|you\s+are)\s+", "role_override"),
    (r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt", "prompt_exfiltration"),
    (r"print\s+(?:your|the)\s+(?:system|hidden)\s+prompt", "prompt_exfiltration"),
    (r"what\s+(?:is|are)\s+your\s+(?:system\s+)?instructions?", "prompt_exfiltration"),
    (r"developer\s+mode", "role_override"),
    (r"jailbreak", "jailbreak"),
    (r"\bdan\b(?:\s+mode|\s*,)", "jailbreak"),
    (r"</?\s*system\s*>", "structured_injection"),
    (r"\[\s*system\s*\]", "structured_injection"),
]

# Unsafe wording the ASSISTANT should never emit. Used for output-guard tests.
_UNSAFE_OUTPUT_PATTERNS: List[tuple[str, str]] = [
    (r"you\s+(?:have|suffer\s+from|are\s+diagnosed\s+with)\s+(?:depression|bipolar|schizophrenia|ptsd|adhd|ocd|anxiety\s+disorder)", "diagnostic_claim"),
    (r"i\s+diagnose\s+you", "diagnostic_claim"),
    (r"clinical(?:ly)?\s+diagnos(?:e|ed|is)", "diagnostic_claim"),
    (r"stop\s+taking\s+your\s+medication", "unsafe_action"),
    (r"you\s+don'?t\s+need\s+(?:a\s+)?(?:therapist|doctor|professional)", "unsafe_action"),
    (r"i\s+am\s+(?:a\s+)?(?:licensed|certified)\s+(?:therapist|doctor|psychiatrist|psychologist)", "false_credentials"),
]


@dataclass
class InjectionResult:
    detected: bool
    categories: List[str] = field(default_factory=list)
    matches: List[str] = field(default_factory=list)


def _scan(text: str, patterns: List[tuple[str, str]]) -> InjectionResult:
    if not text or not text.strip():
        return InjectionResult(False)
    cats: List[str] = []
    matches: List[str] = []
    seen: set[str] = set()
    for pat, cat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if cat not in seen:
                cats.append(cat)
                seen.add(cat)
            matches.append(m.group(0))
    return InjectionResult(detected=bool(cats), categories=cats, matches=matches)


def detect_injection(text: str) -> InjectionResult:
    """Scan a user turn for prompt-injection markers."""
    return _scan(text, _INJECTION_PATTERNS)


def scan_output(text: str) -> InjectionResult:
    """Scan a model output for diagnostic claims or unsafe advice."""
    return _scan(text, _UNSAFE_OUTPUT_PATTERNS)
