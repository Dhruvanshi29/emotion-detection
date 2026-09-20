"""Journal reflection service (plan §4).

Uses the shared LLM router to generate a gentle summary, themes, and a single
open reflection question for a journal entry. Never diagnostic. Falls back to
a template-based reflection derived from the lexicon emotion analyzer when the
LLM is unavailable or returns unparseable output.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from app.services.ai.llm import ChatMessage, LLMProviderError
from app.services.ai.llm.router import LLMRouter
from app.services.emotion.text import _lexicon_analyze  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


@dataclass
class JournalReflection:
    summary: str
    reflection_prompt: str
    themes: List[str] = field(default_factory=list)
    key_feelings: List[str] = field(default_factory=list)
    dominant_emotion: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class JournalReflector(Protocol):
    async def reflect(
        self, *, title: Optional[str], content: str, mood: Optional[int]
    ) -> JournalReflection: ...


_SYSTEM_PROMPT = """\
You are a warm, non-judgmental journaling companion. You do NOT diagnose and \
you do NOT give medical or clinical advice.

Read the user's journal entry and return ONLY a compact JSON object with this \
exact shape:

{
  "summary": "1-3 gentle sentences reflecting what the writer shared.",
  "themes": ["short theme phrase", "another"],
  "key_feelings": ["tentative feeling word", "another"],
  "dominant_emotion": "joy|sadness|anger|fear|surprise|disgust|neutral",
  "sentiment": "positive|neutral|negative",
  "confidence": 0.0,
  "reflection_prompt": "One warm, open-ended question inviting further reflection."
}

Rules:
- Use tentative language ("it sounds like", "you might be", "one thing that \
  sometimes helps") — never claim clinical certainty.
- Themes: 2-5 phrases, each <=6 words.
- Key feelings: 1-5 tentative feeling words.
- reflection_prompt: exactly one gentle, open question. Not advice.
- Do not name a diagnosis or medication.
- Do not mention self-harm resources unless the entry describes urgent risk; \
  that is handled elsewhere.
- Return ONLY the JSON object. No prose, no code fences.\
"""


class LLMJournalReflector:
    def __init__(
        self,
        router: LLMRouter,
        *,
        max_tokens: int = 500,
        temperature: float = 0.4,
    ) -> None:
        self._router = router
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def reflect(
        self, *, title: Optional[str], content: str, mood: Optional[int]
    ) -> JournalReflection:
        content = (content or "").strip()
        if not content:
            return _fallback_reflection("", mood)

        user_block = _format_entry(title=title, content=content, mood=mood)
        prompt = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_block),
        ]
        try:
            resp = await self._router.complete(
                prompt,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except LLMProviderError as e:
            logger.warning("journal.llm failed, falling back: %s", e)
            return _fallback_reflection(content, mood)

        parsed = _extract_json(resp.text)
        if parsed is None:
            logger.warning(
                "journal.llm returned unparseable text: %r", resp.text[:200]
            )
            fb = _fallback_reflection(content, mood)
            fb.provider = resp.provider
            fb.model = resp.model
            return fb

        return _coerce_reflection(parsed, provider=resp.provider, model=resp.model)


def _format_entry(*, title: Optional[str], content: str, mood: Optional[int]) -> str:
    parts: List[str] = []
    if title:
        parts.append(f"Title: {title.strip()[:200]}")
    if mood is not None:
        parts.append(f"Self-reported mood (1-5): {mood}")
    parts.append("Entry:")
    parts.append(content[:8000])
    return "\n".join(parts)


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


_EMOTIONS = ("joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral")
_SENTIMENTS = ("positive", "neutral", "negative")


def _coerce_reflection(
    data: dict, *, provider: Optional[str], model: Optional[str]
) -> JournalReflection:
    summary = _clean_str(data.get("summary"), max_len=600) or (
        "Thank you for taking a moment to write this down."
    )
    reflection_prompt = _clean_str(
        data.get("reflection_prompt"), max_len=300
    ) or "What feels like the most important thing in what you just wrote?"

    themes = _clean_list(data.get("themes"), max_items=5, max_len=64)
    key_feelings = _clean_list(data.get("key_feelings"), max_items=5, max_len=32)

    dom = str(data.get("dominant_emotion") or "").lower()
    dominant = dom if dom in _EMOTIONS else None

    sent = str(data.get("sentiment") or "").lower()
    sentiment = sent if sent in _SENTIMENTS else None

    conf: Optional[float]
    try:
        conf = float(data["confidence"])  # type: ignore[index]
        conf = max(0.0, min(1.0, conf))
    except (KeyError, TypeError, ValueError):
        conf = None

    return JournalReflection(
        summary=summary,
        reflection_prompt=reflection_prompt,
        themes=themes,
        key_feelings=key_feelings,
        dominant_emotion=dominant,
        sentiment=sentiment,
        confidence=conf,
        provider=provider,
        model=model,
    )


def _clean_str(v, *, max_len: int) -> Optional[str]:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s[:max_len] if s else None


def _clean_list(v, *, max_items: int, max_len: int) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v[:max_items]:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:max_len])
    return out


# ---------- Fallback ----------

_PROMPTS_BY_EMOTION: Dict[str, str] = {
    "joy": "What do you want to remember about this feeling later?",
    "sadness": "If a caring friend were reading this, what might they gently say to you?",
    "anger": "What need or value of yours feels unheard right now?",
    "fear": "What is one small thing that would help you feel a little safer?",
    "surprise": "What surprised you most, and what does that tell you about what matters?",
    "disgust": "What boundary or value is this reaction pointing you toward?",
    "neutral": "What is one small thing you'd like to notice about today?",
}


def _fallback_reflection(content: str, mood: Optional[int]) -> JournalReflection:
    emo = _lexicon_analyze(content) if content else None

    if emo and emo.dominant_emotion in _PROMPTS_BY_EMOTION:
        dominant = emo.dominant_emotion
        sentiment = emo.sentiment
        confidence = emo.confidence
        key_feelings = list(emo.signals[:3])
    else:
        dominant = "neutral"
        sentiment = "neutral"
        confidence = 0.0
        key_feelings = []

    if mood is not None and mood <= 2 and dominant == "neutral":
        dominant = "sadness"
        sentiment = "negative"

    summary_bits: List[str] = []
    if mood is not None:
        mood_word = {1: "very low", 2: "low", 3: "mixed", 4: "good", 5: "very good"}.get(
            mood, "mixed"
        )
        summary_bits.append(f"You noted your mood as {mood_word}.")
    if dominant != "neutral":
        summary_bits.append(
            f"There are signals that suggest some {dominant} in what you wrote."
        )
    else:
        summary_bits.append("Thank you for taking a moment to reflect.")

    return JournalReflection(
        summary=" ".join(summary_bits),
        reflection_prompt=_PROMPTS_BY_EMOTION.get(
            dominant, _PROMPTS_BY_EMOTION["neutral"]
        ),
        themes=[],
        key_feelings=key_feelings,
        dominant_emotion=dominant,
        sentiment=sentiment,
        confidence=confidence,
        provider="fallback",
        model="template-v1",
    )
