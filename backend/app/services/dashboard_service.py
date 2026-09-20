"""Dashboard aggregations (Phase 10).

All computations here are read-only, per-user, and derive their windows from
UTC day boundaries. Buckets are computed in Python from the returned rows —
avoids per-dialect date-truncation SQL — which is fine at the sizes we
support (window ≤ 90 days).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation, Message, RiskAssessment
from app.models.emotion import EMOTIONS, EmotionEvent
from app.models.facial import FacialAnalysis
from app.models.journal import JournalEntry
from app.models.reminder import Notification, Reminder
from app.models.voice import VoiceAnalysis
from app.models.wellness import ExerciseSession, UserGoal, WellnessExercise

SENTIMENTS = ("positive", "neutral", "negative")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _window_start(window_days: int, now: Optional[datetime] = None) -> datetime:
    now = now or _utcnow()
    return now - timedelta(days=window_days)


def _sentiment_weight(s: str) -> float:
    if s == "positive":
        return 1.0
    if s == "negative":
        return -1.0
    return 0.0


def _to_utc_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #


async def build_summary(
    db: AsyncSession, *, user_id: str, window_days: int = 7
) -> Dict:
    now = _utcnow()
    start = _window_start(window_days, now)

    # Chat + conversations
    total_msgs = int(
        (
            await db.execute(
                select(func.count(Message.id))
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.user_id == user_id,
                    Message.created_at >= start,
                )
            )
        ).scalar_one()
    )
    total_convos = int(
        (
            await db.execute(
                select(func.count(Conversation.id)).where(
                    Conversation.user_id == user_id,
                    Conversation.updated_at >= start,
                )
            )
        ).scalar_one()
    )

    # Journal
    total_journal = int(
        (
            await db.execute(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.created_at >= start,
                )
            )
        ).scalar_one()
    )
    avg_mood = (
        await db.execute(
            select(func.avg(JournalEntry.mood)).where(
                JournalEntry.user_id == user_id,
                JournalEntry.created_at >= start,
                JournalEntry.mood.is_not(None),
            )
        )
    ).scalar()

    # Wellness sessions (completed only)
    total_wellness = int(
        (
            await db.execute(
                select(func.count(ExerciseSession.id)).where(
                    ExerciseSession.user_id == user_id,
                    ExerciseSession.completed_at.is_not(None),
                    ExerciseSession.completed_at >= start,
                )
            )
        ).scalar_one()
    )
    avg_rating = (
        await db.execute(
            select(func.avg(ExerciseSession.rating)).where(
                ExerciseSession.user_id == user_id,
                ExerciseSession.rating.is_not(None),
                ExerciseSession.completed_at >= start,
            )
        )
    ).scalar()

    # Emotion events (aggregate)
    ev_rows = list(
        (
            await db.execute(
                select(
                    EmotionEvent.dominant_emotion,
                    EmotionEvent.sentiment,
                    EmotionEvent.source,
                    EmotionEvent.created_at,
                ).where(
                    EmotionEvent.user_id == user_id,
                    EmotionEvent.created_at >= start,
                )
            )
        ).all()
    )
    emo_counter: Counter[str] = Counter(r[0] for r in ev_rows)
    sent_counter: Counter[str] = Counter(r[1] for r in ev_rows)
    total_events = len(ev_rows)
    dominant_emotion, dominant_pct = None, 0.0
    if total_events:
        dominant_emotion, top_n = emo_counter.most_common(1)[0]
        dominant_pct = round(100.0 * top_n / total_events, 1)

    def _pct(k: str) -> float:
        return round(100.0 * sent_counter.get(k, 0) / total_events, 1) if total_events else 0.0

    # Multimodal
    total_voice = int(
        (
            await db.execute(
                select(func.count(VoiceAnalysis.id)).where(
                    VoiceAnalysis.user_id == user_id,
                    VoiceAnalysis.created_at >= start,
                )
            )
        ).scalar_one()
    )
    total_facial = int(
        (
            await db.execute(
                select(func.count(FacialAnalysis.id)).where(
                    FacialAnalysis.user_id == user_id,
                    FacialAnalysis.created_at >= start,
                )
            )
        ).scalar_one()
    )

    # Reminders / goals / notifications (current state, not window-bounded)
    active_reminders = int(
        (
            await db.execute(
                select(func.count(Reminder.id)).where(
                    Reminder.user_id == user_id, Reminder.is_active.is_(True)
                )
            )
        ).scalar_one()
    )
    active_goals = int(
        (
            await db.execute(
                select(func.count(UserGoal.id)).where(
                    UserGoal.user_id == user_id, UserGoal.is_active.is_(True)
                )
            )
        ).scalar_one()
    )
    unread_notifs = int(
        (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()
    )

    # Latest risk (from RiskAssessment via Message → Conversation)
    risk_q = (
        select(RiskAssessment.level, RiskAssessment.created_at)
        .join(Message, RiskAssessment.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id)
        .order_by(RiskAssessment.created_at.desc())
        .limit(1)
    )
    risk_row = (await db.execute(risk_q)).first()
    latest_risk = risk_row[0] if risk_row else None

    # Streaks over last window_days
    activity_dates = await _activity_dates(
        db, user_id=user_id, since=_window_start(max(window_days, 30), now)
    )
    current_streak, longest_streak = _compute_streaks(activity_dates, today=now.date())

    return {
        "window_days": window_days,
        "total_chat_messages": total_msgs,
        "total_conversations": total_convos,
        "total_journal_entries": total_journal,
        "total_wellness_sessions": total_wellness,
        "total_emotion_events": total_events,
        "total_voice_analyses": total_voice,
        "total_facial_analyses": total_facial,
        "active_reminders": active_reminders,
        "active_goals": active_goals,
        "unread_notifications": unread_notifs,
        "dominant_emotion": dominant_emotion,
        "dominant_emotion_percent": dominant_pct,
        "sentiment_positive_pct": _pct("positive"),
        "sentiment_neutral_pct": _pct("neutral"),
        "sentiment_negative_pct": _pct("negative"),
        "average_journal_mood": (
            round(float(avg_mood), 2) if avg_mood is not None else None
        ),
        "average_exercise_rating": (
            round(float(avg_rating), 2) if avg_rating is not None else None
        ),
        "current_streak_days": current_streak,
        "longest_streak_days": longest_streak,
        "latest_risk_level": latest_risk,
        "generated_at": now,
    }


# --------------------------------------------------------------------------- #
# Emotions breakdown
# --------------------------------------------------------------------------- #


async def build_emotions(
    db: AsyncSession, *, user_id: str, window_days: int = 30
) -> Dict:
    now = _utcnow()
    start = _window_start(window_days, now)

    rows = list(
        (
            await db.execute(
                select(
                    EmotionEvent.dominant_emotion,
                    EmotionEvent.sentiment,
                    EmotionEvent.source,
                    EmotionEvent.created_at,
                ).where(
                    EmotionEvent.user_id == user_id,
                    EmotionEvent.created_at >= start,
                )
            )
        ).all()
    )
    by_emotion: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_sentiment: Counter[str] = Counter()
    per_day: Dict[date, Counter[str]] = {}
    for e, s, src, ts in rows:
        by_emotion[e] += 1
        by_source[src] += 1
        by_sentiment[s] += 1
        d = _to_utc_date(ts)
        per_day.setdefault(d, Counter())[e] += 1

    daily = []
    d = start.date()
    end_d = now.date()
    while d <= end_d:
        c = per_day.get(d, Counter())
        daily.append(
            {
                "date": d,
                "counts": {k: int(v) for k, v in c.items()},
            }
        )
        d = d + timedelta(days=1)

    return {
        "window_days": window_days,
        "by_emotion": {k: int(v) for k, v in by_emotion.items()},
        "by_source": {k: int(v) for k, v in by_source.items()},
        "by_sentiment": {k: int(v) for k, v in by_sentiment.items()},
        "daily": daily,
        "total": len(rows),
    }


# --------------------------------------------------------------------------- #
# Trends
# --------------------------------------------------------------------------- #


async def build_trends(
    db: AsyncSession, *, user_id: str, window_days: int = 30
) -> Dict:
    now = _utcnow()
    start = _window_start(window_days, now)

    ev_rows = list(
        (
            await db.execute(
                select(
                    EmotionEvent.sentiment,
                    EmotionEvent.confidence,
                    EmotionEvent.created_at,
                ).where(
                    EmotionEvent.user_id == user_id,
                    EmotionEvent.created_at >= start,
                )
            )
        ).all()
    )
    j_rows = list(
        (
            await db.execute(
                select(JournalEntry.mood, JournalEntry.created_at).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.created_at >= start,
                )
            )
        ).all()
    )
    x_rows = list(
        (
            await db.execute(
                select(
                    ExerciseSession.rating, ExerciseSession.completed_at
                ).where(
                    ExerciseSession.user_id == user_id,
                    ExerciseSession.completed_at.is_not(None),
                    ExerciseSession.completed_at >= start,
                )
            )
        ).all()
    )

    per_day_mood_num: Dict[date, float] = {}
    per_day_mood_den: Dict[date, float] = {}
    per_day_events: Counter[date] = Counter()
    for s, c, ts in ev_rows:
        d = _to_utc_date(ts)
        w = max(float(c or 0.0), 0.1)
        per_day_mood_num[d] = per_day_mood_num.get(d, 0.0) + _sentiment_weight(s) * w
        per_day_mood_den[d] = per_day_mood_den.get(d, 0.0) + w
        per_day_events[d] += 1

    per_day_journal_num: Dict[date, int] = {}
    per_day_journal_cnt: Counter[date] = Counter()
    per_day_journal_mood_sum: Dict[date, int] = {}
    per_day_journal_mood_cnt: Counter[date] = Counter()
    for mood, ts in j_rows:
        d = _to_utc_date(ts)
        per_day_journal_cnt[d] += 1
        per_day_journal_num[d] = per_day_journal_num.get(d, 0) + 1
        if mood is not None:
            per_day_journal_mood_sum[d] = (
                per_day_journal_mood_sum.get(d, 0) + int(mood)
            )
            per_day_journal_mood_cnt[d] += 1

    per_day_ex_cnt: Counter[date] = Counter()
    per_day_ex_rating_sum: Dict[date, int] = {}
    per_day_ex_rating_cnt: Counter[date] = Counter()
    for rating, ts in x_rows:
        d = _to_utc_date(ts)
        per_day_ex_cnt[d] += 1
        if rating is not None:
            per_day_ex_rating_sum[d] = per_day_ex_rating_sum.get(d, 0) + int(rating)
            per_day_ex_rating_cnt[d] += 1

    points = []
    d = start.date()
    end_d = now.date()
    while d <= end_d:
        den = per_day_mood_den.get(d, 0.0)
        mood_score = (
            round(per_day_mood_num.get(d, 0.0) / den, 3) if den > 0 else None
        )
        j_mood_avg = (
            round(
                per_day_journal_mood_sum[d] / per_day_journal_mood_cnt[d],
                2,
            )
            if per_day_journal_mood_cnt.get(d)
            else None
        )
        x_rating_avg = (
            round(
                per_day_ex_rating_sum[d] / per_day_ex_rating_cnt[d],
                2,
            )
            if per_day_ex_rating_cnt.get(d)
            else None
        )
        points.append(
            {
                "date": d,
                "mood_score": mood_score,
                "events": int(per_day_events.get(d, 0)),
                "journal_entries": int(per_day_journal_cnt.get(d, 0)),
                "exercise_sessions": int(per_day_ex_cnt.get(d, 0)),
                "journal_mood_avg": j_mood_avg,
                "exercise_rating_avg": x_rating_avg,
            }
        )
        d = d + timedelta(days=1)

    tail = [p for p in points[-7:] if p["mood_score"] is not None]
    rolling_7 = (
        round(sum(p["mood_score"] for p in tail) / len(tail), 3) if tail else None
    )
    momentum = _momentum(points)

    return {
        "window_days": window_days,
        "granularity": "day",
        "points": points,
        "rolling_mood_7d": rolling_7,
        "momentum": momentum,
    }


def _momentum(points: List[Dict]) -> str:
    tail = [p["mood_score"] for p in points[-7:] if p["mood_score"] is not None]
    prev = [p["mood_score"] for p in points[-14:-7] if p["mood_score"] is not None]
    if len(tail) < 2 or len(prev) < 2:
        return "insufficient_data"
    a = sum(tail) / len(tail)
    b = sum(prev) / len(prev)
    delta = a - b
    if delta > 0.15:
        return "up"
    if delta < -0.15:
        return "down"
    return "steady"


# --------------------------------------------------------------------------- #
# Insights
# --------------------------------------------------------------------------- #


async def build_insights(
    db: AsyncSession, *, user_id: str, window_days: int = 7
) -> Dict:
    now = _utcnow()
    start = _window_start(window_days, now)
    prev_start = _window_start(window_days * 2, now)
    prev_end = start

    highlights: List[str] = []

    j_now = int(
        (
            await db.execute(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.created_at >= start,
                )
            )
        ).scalar_one()
    )
    j_prev = int(
        (
            await db.execute(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.created_at >= prev_start,
                    JournalEntry.created_at < prev_end,
                )
            )
        ).scalar_one()
    )
    if j_now or j_prev:
        arrow = "↑" if j_now > j_prev else ("↓" if j_now < j_prev else "→")
        highlights.append(
            f"Journaled {j_now} day(s) this window {arrow} vs {j_prev} previously."
        )

    x_now = int(
        (
            await db.execute(
                select(func.count(ExerciseSession.id)).where(
                    ExerciseSession.user_id == user_id,
                    ExerciseSession.completed_at.is_not(None),
                    ExerciseSession.completed_at >= start,
                )
            )
        ).scalar_one()
    )
    if x_now:
        highlights.append(f"Completed {x_now} wellness exercise session(s).")

    top_cat_row = (
        await db.execute(
            select(WellnessExercise.category, func.count(ExerciseSession.id).label("n"))
            .join(WellnessExercise, ExerciseSession.exercise_id == WellnessExercise.id)
            .where(
                ExerciseSession.user_id == user_id,
                ExerciseSession.completed_at.is_not(None),
                ExerciseSession.completed_at >= start,
            )
            .group_by(WellnessExercise.category)
            .order_by(func.count(ExerciseSession.id).desc())
            .limit(1)
        )
    ).first()
    top_category = top_cat_row[0] if top_cat_row else None
    if top_category:
        highlights.append(f"Most-used exercise category: {top_category}.")

    emo_rows = list(
        (
            await db.execute(
                select(EmotionEvent.dominant_emotion).where(
                    EmotionEvent.user_id == user_id,
                    EmotionEvent.created_at >= start,
                )
            )
        ).all()
    )
    top_emotion = None
    if emo_rows:
        counter = Counter(r[0] for r in emo_rows)
        top_emotion, n = counter.most_common(1)[0]
        pct = round(100.0 * n / len(emo_rows), 1)
        highlights.append(
            f"Most frequent signal: {top_emotion} ({pct}% of {len(emo_rows)} events). "
            "This is an AI-generated pattern, not a diagnosis."
        )

    activity_dates = await _activity_dates(
        db, user_id=user_id, since=_window_start(max(window_days, 30), now)
    )
    current_streak, longest = _compute_streaks(activity_dates, today=now.date())
    if longest:
        highlights.append(
            f"Longest activity streak in the last {max(window_days, 30)} days: "
            f"{longest} day(s) (currently {current_streak})."
        )

    return {
        "window_days": window_days,
        "highlights": highlights,
        "top_emotion": top_emotion,
        "top_exercise_category": top_category,
    }


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


async def _activity_dates(
    db: AsyncSession, *, user_id: str, since: datetime
) -> List[date]:
    dates: set[date] = set()
    for table_col, where in (
        (EmotionEvent.created_at, EmotionEvent.user_id == user_id),
        (JournalEntry.created_at, JournalEntry.user_id == user_id),
        (ExerciseSession.started_at, ExerciseSession.user_id == user_id),
    ):
        rows = (
            await db.execute(
                select(table_col).where(where, table_col >= since)
            )
        ).all()
        for (ts,) in rows:
            dates.add(_to_utc_date(ts))
    return sorted(dates)


def _compute_streaks(dates: List[date], *, today: date) -> Tuple[int, int]:
    if not dates:
        return 0, 0
    dset = set(dates)
    # Current streak — walk back from today.
    cur = 0
    cursor = today
    while cursor in dset:
        cur += 1
        cursor = cursor - timedelta(days=1)
    # Longest streak — scan sorted dates.
    longest = 0
    run = 0
    prev: Optional[date] = None
    for d in sorted(dates):
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run = 1
        prev = d
        longest = max(longest, run)
    return cur, longest


__all__ = [
    "build_summary",
    "build_emotions",
    "build_trends",
    "build_insights",
    "EMOTIONS",
    "SENTIMENTS",
]
