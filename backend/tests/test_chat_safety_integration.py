"""Chat service safety integration (Phase 13).

Tests the risk-classification, LLM-error fallback, and unsafe-output guard
paths directly against `chat_service.send_message` — no HTTP layer.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Message, RiskAssessment, SafetyEvent
from app.models.user import User
from app.services import chat_service
from app.services.ai.llm import ChatMessage, LLMResponse
from app.services.ai.llm.base import LLMProviderError


class _EchoRouter:
    async def complete(self, messages, **_kw):
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(
            text=f"I hear you: {last}", provider="stub", model="stub-1"
        )


class _FailingRouter:
    async def complete(self, messages, **_kw):
        raise LLMProviderError("stub", "unavailable")


class _UnsafeOutputRouter:
    async def complete(self, messages, **_kw):
        return LLMResponse(
            text="Based on what you've said, you have depression.",
            provider="stub",
            model="stub-1",
        )


async def _make_user(sess: AsyncSession, email: str) -> str:
    u = User(email=email, hashed_password="x")
    sess.add(u)
    await sess.commit()
    await sess.refresh(u)
    return u.id


@pytest.mark.asyncio
async def test_high_risk_input_persists_safe_reply_and_safety_event(test_engine):
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as sess:
        uid = await _make_user(sess, "cs-highrisk@example.com")

    async with SessionLocal() as sess:
        result = await chat_service.send_message(
            sess,
            _EchoRouter(),  # type: ignore[arg-type]
            user_id=uid,
            conversation_id=None,
            content="I want to end my life tonight",
        )
    assert result.risk_level == "high"
    assert "988" in result.assistant_message.content
    assert result.assistant_message.provider == "safety"

    async with SessionLocal() as sess:
        risks = (
            await sess.execute(
                select(RiskAssessment).where(
                    RiskAssessment.message_id == result.user_message.id
                )
            )
        ).scalars().all()
        assert len(risks) == 1
        assert risks[0].level == "high"

        events = (
            await sess.execute(
                select(SafetyEvent).where(SafetyEvent.user_id == uid)
            )
        ).scalars().all()
        assert any(e.event_type == "high_risk_safe_reply" for e in events)


@pytest.mark.asyncio
async def test_llm_provider_error_returns_static_fallback(test_engine):
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as sess:
        uid = await _make_user(sess, "cs-llmfail@example.com")

    async with SessionLocal() as sess:
        result = await chat_service.send_message(
            sess,
            _FailingRouter(),  # type: ignore[arg-type]
            user_id=uid,
            conversation_id=None,
            content="How was your day?",
        )
    assert result.assistant_message.provider == "fallback"
    assert "trouble" in result.assistant_message.content.lower()


@pytest.mark.asyncio
async def test_unsafe_llm_output_is_rewritten_and_flagged(test_engine):
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as sess:
        uid = await _make_user(sess, "cs-unsafeout@example.com")

    async with SessionLocal() as sess:
        result = await chat_service.send_message(
            sess,
            _UnsafeOutputRouter(),  # type: ignore[arg-type]
            user_id=uid,
            conversation_id=None,
            content="I've been down a lot lately",
        )
    assert result.assistant_message.provider == "safety"
    assert "you have depression" not in result.assistant_message.content.lower()
    assert result.assistant_message.model == "output-guard-v1"

    async with SessionLocal() as sess:
        events = (
            await sess.execute(
                select(SafetyEvent).where(SafetyEvent.user_id == uid)
            )
        ).scalars().all()
        assert any(e.event_type == "unsafe_output_rewritten" for e in events)


@pytest.mark.asyncio
async def test_normal_message_persists_assistant_reply_no_safety_event(test_engine):
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as sess:
        uid = await _make_user(sess, "cs-normal@example.com")

    async with SessionLocal() as sess:
        result = await chat_service.send_message(
            sess,
            _EchoRouter(),  # type: ignore[arg-type]
            user_id=uid,
            conversation_id=None,
            content="Tell me a bedtime story",
        )
    assert result.risk_level == "none"
    assert result.assistant_message.provider == "stub"
    assert "I hear you" in result.assistant_message.content

    async with SessionLocal() as sess:
        events = (
            await sess.execute(
                select(SafetyEvent).where(SafetyEvent.user_id == uid)
            )
        ).scalars().all()
        assert events == []
        msgs = (
            await sess.execute(
                select(Message).where(
                    Message.conversation_id == result.conversation.id
                )
            )
        ).scalars().all()
        assert len(msgs) == 2  # user + assistant
