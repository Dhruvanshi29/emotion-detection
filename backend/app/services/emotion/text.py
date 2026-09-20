"""Text emotion service (plan §10, §13).

- Uses the shared LLM router to extract a structured emotion profile from text.
- Uses tentative "signals" language, never diagnostic.
- Falls back to a lightweight lexicon-based analyzer if the LLM is unavailable
  or returns unparseable output.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from app.models.emotion import EMOTIONS
from app.services.ai.llm import ChatMessage, LLMProviderError
from app.services.ai.llm.router import LLMRouter

logger = logging.getLogger(__name__)


SENTIMENTS = ("positive", "neutral", "negative")


@dataclass
class TextEmotionResult:
    dominant_emotion: str
    sentiment: str
    confidence: float
    scores: Dict[str, float]
    signals: List[str] = field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None


class EmotionAnalyzer(Protocol):
    async def analyze(self, text: str) -> TextEmotionResult: ...


# ---------- LLM-backed analyzer ----------


_SYSTEM_PROMPT = """\
You are an emotion signal extractor. You do NOT diagnose. Read the user's short \
text and return ONLY a compact JSON object with this exact shape:

{
  "scores": {"joy": 0.0, "sadness": 0.0, "anger": 0.0, "fear": 0.0, "surprise": 0.0, "disgust": 0.0, "neutral": 0.0},
  "dominant_emotion": "joy|sadness|anger|fear|surprise|disgust|neutral",
  "sentiment": "positive|neutral|negative",
  "confidence": 0.0,
  "signals": ["short phrase 1", "short phrase 2"]
}

Rules:
- All scores are between 0 and 1 and should sum to about 1.
- "signals" are 1-4 short (<=5 word) phrases from the text that most influenced you.
- Use tentative labels only. Never claim clinical certainty.
- Return ONLY the JSON object. No prose, no code fences.\
"""


class LLMEmotionAnalyzer:
    def __init__(self, router: LLMRouter, *, max_tokens: int = 300, temperature: float = 0.0):
        self._router = router
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def analyze(self, text: str) -> TextEmotionResult:
        text = (text or "").strip()
        if not text:
            return _neutral_result()

        prompt = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=text[:4000]),
        ]
        try:
            resp = await self._router.complete(
                prompt, max_tokens=self._max_tokens, temperature=self._temperature
            )
        except LLMProviderError as e:
            logger.warning("emotion.llm failed, falling back: %s", e)
            return _lexicon_analyze(text)

        parsed = _extract_json(resp.text)
        if parsed is None:
            logger.warning("emotion.llm returned unparseable text: %r", resp.text[:200])
            fallback = _lexicon_analyze(text)
            fallback.provider = resp.provider
            fallback.model = resp.model
            return fallback

        return _coerce_result(parsed, provider=resp.provider, model=resp.model)


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


def _coerce_result(
    data: dict, *, provider: Optional[str], model: Optional[str]
) -> TextEmotionResult:
    scores_in = data.get("scores") or {}
    scores: Dict[str, float] = {}
    for name in EMOTIONS:
        v = scores_in.get(name, 0.0)
        try:
            scores[name] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            scores[name] = 0.0

    total = sum(scores.values())
    if total <= 0:
        scores["neutral"] = 1.0
        total = 1.0
    scores = {k: v / total for k, v in scores.items()}

    dom_in = str(data.get("dominant_emotion") or "").lower()
    dominant = dom_in if dom_in in EMOTIONS else max(scores, key=scores.get)

    sent_in = str(data.get("sentiment") or "").lower()
    sentiment = sent_in if sent_in in SENTIMENTS else _sentiment_from_scores(scores)

    try:
        conf = float(data.get("confidence", scores[dominant]))
    except (TypeError, ValueError):
        conf = scores[dominant]
    conf = max(0.0, min(1.0, conf))

    signals_raw = data.get("signals") or []
    signals: List[str] = []
    if isinstance(signals_raw, list):
        for s in signals_raw[:6]:
            if isinstance(s, str) and s.strip():
                signals.append(s.strip()[:64])

    return TextEmotionResult(
        dominant_emotion=dominant,
        sentiment=sentiment,
        confidence=conf,
        scores=scores,
        signals=signals,
        provider=provider,
        model=model,
    )


def _sentiment_from_scores(scores: Dict[str, float]) -> str:
    pos = scores.get("joy", 0.0) + 0.4 * scores.get("surprise", 0.0)
    neg = (
        scores.get("sadness", 0.0)
        + scores.get("anger", 0.0)
        + scores.get("fear", 0.0)
        + scores.get("disgust", 0.0)
    )
    if pos - neg > 0.15:
        return "positive"
    if neg - pos > 0.15:
        return "negative"
    return "neutral"


def _neutral_result() -> TextEmotionResult:
    scores = {name: 0.0 for name in EMOTIONS}
    scores["neutral"] = 1.0
    return TextEmotionResult(
        dominant_emotion="neutral",
        sentiment="neutral",
        confidence=0.0,
        scores=scores,
        signals=[],
    )


# ---------- Lexicon fallback ----------

_LEXICON: Dict[str, List[str]] = {
    "joy": ["happy", "great", "glad", "grateful", "excited", "love", "wonderful", "amazing", "hopeful"],
    "sadness": ["sad", "down", "cry", "cried", "crying", "lonely", "empty", "grief", "hurt", "miss"],
    "anger": ["angry", "furious", "mad", "annoyed", "irritated", "hate", "resent", "frustrated"],
    "fear": ["scared", "afraid", "anxious", "worried", "panicked", "nervous", "terrified"],
    "surprise": ["surprised", "shocked", "unexpected", "wow", "sudden"],
    "disgust": ["disgusted", "sick of", "gross", "repulsed"],
}


def _lexicon_analyze(text: str) -> TextEmotionResult:
    t = text.lower()
    raw: Dict[str, float] = {name: 0.0 for name in EMOTIONS}
    signals: List[str] = []
    for emo, words in _LEXICON.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", t):
                raw[emo] += 1.0
                if w not in signals:
                    signals.append(w)

    total = sum(raw.values())
    if total == 0:
        return _neutral_result()

    scores = {k: v / total for k, v in raw.items()}
    dominant = max(scores, key=scores.get)
    return TextEmotionResult(
        dominant_emotion=dominant,
        sentiment=_sentiment_from_scores(scores),
        confidence=min(0.6, 0.2 + 0.15 * total),
        scores=scores,
        signals=signals[:4],
        provider="lexicon",
        model="fallback-v1",
    )
