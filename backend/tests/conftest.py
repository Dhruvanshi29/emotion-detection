"""Pytest configuration and shared fixtures.

Uses an in-memory SQLite database with a single shared connection so all
sessions see the same schema/rows. Overrides FastAPI's get_db dependency
to route requests through this test engine.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.api.deps import get_emotion_analyzer, get_router, get_stt
from app.api.journal import get_journal_reflector
from app.services.ai.journal import JournalReflection
from app.services.ai.llm import ChatMessage, LLMResponse
from app.services.emotion import TextEmotionResult
from app.services.stt import STTResult

# Import models so metadata is populated.
from app.models import user as _user  # noqa: F401
from app.models import chat as _chat  # noqa: F401
from app.models import emotion as _emotion  # noqa: F401
from app.models import journal as _journal  # noqa: F401
from app.models import voice as _voice  # noqa: F401
from app.models import audit as _audit  # noqa: F401

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


class StubEmotionAnalyzer:
    """Deterministic keyword-based emotion analyzer for tests."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze(self, text: str) -> TextEmotionResult:
        self.calls.append(text)
        low = text.lower()
        if "happy" in low or "great" in low or "amazing" in low:
            dominant, sentiment = "joy", "positive"
            scores = {"joy": 0.8, "sadness": 0.02, "anger": 0.02, "fear": 0.02,
                      "surprise": 0.06, "disgust": 0.02, "neutral": 0.06}
        elif "sad" in low or "lonely" in low or "down" in low:
            dominant, sentiment = "sadness", "negative"
            scores = {"joy": 0.02, "sadness": 0.8, "anger": 0.04, "fear": 0.06,
                      "surprise": 0.02, "disgust": 0.02, "neutral": 0.04}
        elif "angry" in low or "furious" in low:
            dominant, sentiment = "anger", "negative"
            scores = {"joy": 0.02, "sadness": 0.06, "anger": 0.8, "fear": 0.04,
                      "surprise": 0.02, "disgust": 0.02, "neutral": 0.04}
        else:
            dominant, sentiment = "neutral", "neutral"
            scores = {"joy": 0.05, "sadness": 0.05, "anger": 0.05, "fear": 0.05,
                      "surprise": 0.05, "disgust": 0.05, "neutral": 0.70}
        return TextEmotionResult(
            dominant_emotion=dominant,
            sentiment=sentiment,
            confidence=0.9,
            scores=scores,
            signals=["stub signal"],
            provider="stub",
            model="stub-emotion-1",
        )


class StubJournalReflector:
    """Deterministic reflector for tests — no LLM call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str, int | None]] = []

    async def reflect(self, *, title, content, mood):
        self.calls.append((title, content, mood))
        low = (content or "").lower()
        if "sad" in low or "lonely" in low:
            dom, sent = "sadness", "negative"
            feelings = ["down", "lonely"]
        elif "happy" in low or "great" in low:
            dom, sent = "joy", "positive"
            feelings = ["hopeful"]
        else:
            dom, sent = "neutral", "neutral"
            feelings = []
        return JournalReflection(
            summary=f"[stub summary] {content[:60]}",
            reflection_prompt="What feels most important about what you just wrote?",
            themes=["stub theme"],
            key_feelings=feelings,
            dominant_emotion=dom,
            sentiment=sent,
            confidence=0.8,
            provider="stub",
            model="stub-journal-1",
        )


class StubLLMRouter:
    """Deterministic in-memory LLM router used across the test suite.

    Echoes back a short reply that includes the last user turn so tests can
    assert content flowed through the system prompt + history pipeline.
    """

    name = "stub"

    def __init__(self):
        self._settings = type("S", (), {"provider_chain": ["stub"]})()
        self.last_prompt: list[ChatMessage] = []

    def available_providers(self):
        return ["stub"]

    async def complete(self, messages, *, preferred=None, max_tokens=None, temperature=None):
        self.last_prompt = list(messages)
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        return LLMResponse(
            text=f"[stub reply] I hear you: {last_user[:80]}",
            provider="stub",
            model="stub-1",
            prompt_tokens=len(messages),
            completion_tokens=8,
        )

    async def stream(self, messages, *, preferred=None, max_tokens=None, temperature=None):
        yield "[stub reply]"


class StubSTTRouter:
    """Deterministic STT router — decodes a short marker embedded in the audio bytes.

    Tests can prefix their fake audio bytes with e.g. b'SAD:' to force the
    resulting transcript to include 'sad and lonely'. Falls back to a neutral
    transcript otherwise.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self._settings = type(
            "S", (), {"stt_provider_chain_list": ["stub"]}
        )()

    def available_providers(self) -> list[str]:
        return ["stub"]

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language=None,
        preferred=None,
    ) -> STTResult:
        self.calls.append((filename, content_type, len(audio)))
        if b"SAD:" in audio:
            text = "I feel sad and lonely tonight."
        elif b"JOY:" in audio:
            text = "I feel so happy and grateful today."
        elif b"ANGRY:" in audio:
            text = "I am so angry and furious right now."
        else:
            text = "This is a neutral test recording."
        return STTResult(
            text=text,
            provider="stub",
            model="stub-whisper-1",
            language="en",
            duration_seconds=2.5,
            segments=[],
        )


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed the wellness catalog once so /wellness endpoints have content.
    SessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    from app.services import wellness_service as _wellness
    from app.services import therapist_service as _therapist
    async with SessionLocal() as db:
        await _wellness.ensure_seed(db)
        await _therapist.ensure_seed(db)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def client(test_engine) -> AsyncIterator[AsyncClient]:
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    stub = StubLLMRouter()
    app.dependency_overrides[get_router] = lambda: stub
    emotion_stub = StubEmotionAnalyzer()
    app.dependency_overrides[get_emotion_analyzer] = lambda: emotion_stub
    journal_stub = StubJournalReflector()
    app.dependency_overrides[get_journal_reflector] = lambda: journal_stub
    stt_stub = StubSTTRouter()
    app.dependency_overrides[get_stt] = lambda: stt_stub

    # Patch app.db.session.SessionLocal so BackgroundTasks that open their
    # own session use the test engine.
    import app.db.session as _session_mod
    original_session_local = _session_mod.SessionLocal
    _session_mod.SessionLocal = SessionLocal  # type: ignore[assignment]

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.stub_llm = stub  # type: ignore[attr-defined]
            ac.stub_emotion = emotion_stub  # type: ignore[attr-defined]
            ac.stub_journal = journal_stub  # type: ignore[attr-defined]
            ac.stub_stt = stt_stub  # type: ignore[attr-defined]
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_router, None)
        app.dependency_overrides.pop(get_emotion_analyzer, None)
        app.dependency_overrides.pop(get_journal_reflector, None)
        app.dependency_overrides.pop(get_stt, None)
        _session_mod.SessionLocal = original_session_local  # type: ignore[assignment]
