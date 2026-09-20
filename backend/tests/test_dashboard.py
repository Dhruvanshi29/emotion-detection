"""Dashboard aggregations (Phase 10).

We seed test data directly through the ORM so the assertions can pin exact
counts and dominant emotions without depending on the fuzzy behavior of the
real emotion/LLM services.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chat import Conversation, Message, RiskAssessment
from app.models.emotion import EmotionEvent
from app.models.journal import JournalEntry
from app.models.user import User
from app.models.wellness import ExerciseSession, WellnessExercise
from app.services.dashboard_service import _compute_streaks


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "D"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user_id(sess: AsyncSession, email: str) -> str:
    row = (await sess.execute(select(User).where(User.email == email))).scalar_one()
    return row.id


async def _seed(engine, email: str) -> str:
    """Populate emotion/chat/journal/exercise history for a user."""
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        uid = await _user_id(db, email)
        now = _now()

        # Emotion events: 4 sadness/negative, 2 joy/positive over last 3 days.
        events = [
            ("chat", "sadness", "negative", 0.8, now - timedelta(days=0, hours=2)),
            ("chat", "sadness", "negative", 0.6, now - timedelta(days=1, hours=4)),
            ("journal", "joy", "positive", 0.9, now - timedelta(days=1, hours=1)),
            ("voice", "sadness", "negative", 0.7, now - timedelta(days=2, hours=3)),
            ("face", "sadness", "negative", 0.5, now - timedelta(days=2, hours=1)),
            ("journal", "joy", "positive", 0.8, now - timedelta(days=3, hours=1)),
        ]
        for src, dom, sent, conf, ts in events:
            ev = EmotionEvent(
                user_id=uid,
                source=src,
                dominant_emotion=dom,
                sentiment=sent,
                confidence=conf,
                created_at=ts,
            )
            db.add(ev)

        # Journal entries with self-mood
        db.add(
            JournalEntry(
                user_id=uid,
                content="Hard day today.",
                mood=2,
                created_at=now - timedelta(days=0, hours=1),
            )
        )
        db.add(
            JournalEntry(
                user_id=uid,
                content="Better.",
                mood=4,
                created_at=now - timedelta(days=1, hours=2),
            )
        )

        # Conversation + assistant message + risk assessment (medium)
        conv = Conversation(user_id=uid, title="test")
        db.add(conv)
        await db.flush()
        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="I hear you.",
            created_at=now - timedelta(hours=3),
        )
        db.add(msg)
        await db.flush()
        db.add(
            RiskAssessment(
                message_id=msg.id,
                level="medium",
                created_at=now - timedelta(hours=3),
            )
        )

        # Completed wellness session
        ex = (
            await db.execute(
                select(WellnessExercise).where(
                    WellnessExercise.slug == "box-breathing-4-4-4-4"
                )
            )
        ).scalar_one()
        db.add(
            ExerciseSession(
                user_id=uid,
                exercise_id=ex.id,
                started_at=now - timedelta(days=0, hours=4),
                completed_at=now - timedelta(days=0, hours=3, minutes=55),
                rating=5,
            )
        )

        await db.commit()
        return uid


# --------------------------------------------------------------------------- #
# Pure helper
# --------------------------------------------------------------------------- #


def test_streaks_current_and_longest():
    from datetime import date

    today = date(2026, 8, 30)
    dates = [
        date(2026, 8, 20),
        date(2026, 8, 21),
        date(2026, 8, 22),  # 3-day run
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 28),
        date(2026, 8, 29),
        date(2026, 8, 30),  # current 3-day run to today
    ]
    cur, longest = _compute_streaks(dates, today=today)
    assert cur == 3
    assert longest == 3

    # No activity today → current streak 0
    dates2 = [date(2026, 8, 28), date(2026, 8, 29)]
    cur2, longest2 = _compute_streaks(dates2, today=today)
    assert cur2 == 0
    assert longest2 == 2

    assert _compute_streaks([], today=today) == (0, 0)


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_summary_requires_auth(client):
    r = await client.get("/dashboard/summary")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_summary_reflects_seeded_history(client, test_engine):
    email = "dash-summary@example.com"
    h = await _register(client, email)
    await _seed(test_engine, email)

    r = await client.get("/dashboard/summary?window_days=7", headers=h)
    assert r.status_code == 200, r.text
    b = r.json()

    assert b["window_days"] == 7
    assert b["total_emotion_events"] == 6
    assert b["total_journal_entries"] == 2
    assert b["total_wellness_sessions"] == 1
    assert b["total_chat_messages"] == 1
    assert b["total_conversations"] == 1
    assert b["dominant_emotion"] == "sadness"
    # 4 of 6 events are sadness → 66.7%
    assert 60 <= b["dominant_emotion_percent"] <= 70
    # Sentiment percentages sum to 100.
    total_pct = (
        b["sentiment_positive_pct"]
        + b["sentiment_neutral_pct"]
        + b["sentiment_negative_pct"]
    )
    assert 99.0 <= total_pct <= 101.0
    assert b["sentiment_negative_pct"] > b["sentiment_positive_pct"]
    assert b["average_journal_mood"] == 3.0
    assert b["average_exercise_rating"] == 5.0
    assert b["latest_risk_level"] == "medium"
    assert b["current_streak_days"] >= 1
    assert b["longest_streak_days"] >= 1


@pytest.mark.asyncio
async def test_summary_empty_user_returns_zeroes(client):
    h = await _register(client, "dash-empty@example.com")
    r = await client.get("/dashboard/summary", headers=h)
    assert r.status_code == 200
    b = r.json()
    assert b["total_emotion_events"] == 0
    assert b["total_journal_entries"] == 0
    assert b["dominant_emotion"] is None
    assert b["sentiment_positive_pct"] == 0.0
    assert b["current_streak_days"] == 0
    assert b["latest_risk_level"] is None


@pytest.mark.asyncio
async def test_emotions_breakdown(client, test_engine):
    email = "dash-emotions@example.com"
    h = await _register(client, email)
    await _seed(test_engine, email)

    r = await client.get("/dashboard/emotions?window_days=7", headers=h)
    assert r.status_code == 200
    b = r.json()
    assert b["total"] == 6
    assert b["by_emotion"].get("sadness") == 4
    assert b["by_emotion"].get("joy") == 2
    assert b["by_source"].get("chat") == 2
    assert b["by_source"].get("journal") == 2
    assert b["by_source"].get("voice") == 1
    assert b["by_source"].get("face") == 1
    assert b["by_sentiment"].get("negative") == 4
    assert b["by_sentiment"].get("positive") == 2
    # Daily buckets cover window_days + 1 (inclusive today)
    assert len(b["daily"]) == 8


@pytest.mark.asyncio
async def test_trends_series_and_momentum(client, test_engine):
    email = "dash-trends@example.com"
    h = await _register(client, email)
    await _seed(test_engine, email)

    r = await client.get("/dashboard/trends?window_days=30", headers=h)
    assert r.status_code == 200
    b = r.json()
    assert b["granularity"] == "day"
    assert len(b["points"]) == 31
    # Rolling mood: negative-heavy, expect ≤ 0.
    if b["rolling_mood_7d"] is not None:
        assert -1.0 <= b["rolling_mood_7d"] <= 1.0
    assert b["momentum"] in {"up", "down", "steady", "insufficient_data"}
    # Days with events accumulate exercise/journal
    day_with_journal = [p for p in b["points"] if p["journal_entries"] > 0]
    assert day_with_journal, "seeded journal entries should surface in trend points"


@pytest.mark.asyncio
async def test_insights_highlights_and_top_signal(client, test_engine):
    email = "dash-insights@example.com"
    h = await _register(client, email)
    await _seed(test_engine, email)

    r = await client.get("/dashboard/insights?window_days=7", headers=h)
    assert r.status_code == 200
    b = r.json()
    assert b["top_emotion"] == "sadness"
    assert b["top_exercise_category"] == "breathing"
    # Any highlight mentioning the "not a diagnosis" disclaimer for the signal
    joined = " ".join(b["highlights"]).lower()
    assert "not a diagnosis" in joined
    assert "sadness" in joined


@pytest.mark.asyncio
async def test_user_isolation(client, test_engine):
    email_a = "dash-iso-a@example.com"
    email_b = "dash-iso-b@example.com"
    ha = await _register(client, email_a)
    hb = await _register(client, email_b)
    await _seed(test_engine, email_a)

    sb = await client.get("/dashboard/summary", headers=hb)
    assert sb.status_code == 200
    assert sb.json()["total_emotion_events"] == 0

    sa = await client.get("/dashboard/summary", headers=ha)
    assert sa.status_code == 200
    assert sa.json()["total_emotion_events"] == 6


@pytest.mark.asyncio
async def test_window_days_validation(client):
    h = await _register(client, "dash-window@example.com")
    r = await client.get("/dashboard/summary?window_days=0", headers=h)
    assert r.status_code == 422
    r2 = await client.get("/dashboard/summary?window_days=999", headers=h)
    assert r2.status_code == 422
