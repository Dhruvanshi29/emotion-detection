"""Wellness service — deterministic recommendation engine (plan §6 RecommendationService).

Rules-only scoring: no LLM in the loop, no user data leaves this file. Signals
in, ranked exercises out. Content authored per plan §23 governance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.emotion import EmotionEvent
from app.models.wellness import EXERCISE_CATEGORIES, ExerciseSession, UserGoal, WellnessExercise

logger = logging.getLogger(__name__)


# ---------- seed content (small, curated) ----------

SEED_EXERCISES: list[dict] = [
    {
        "slug": "box-breathing-4-4-4-4",
        "title": "Box breathing (4-4-4-4)",
        "summary": "A steady breathing rhythm to settle the nervous system.",
        "category": "breathing",
        "duration_seconds": 180,
        "body": (
            "1. Sit comfortably. Relax your shoulders.\n"
            "2. Inhale through your nose for 4 seconds.\n"
            "3. Hold for 4 seconds.\n"
            "4. Exhale slowly through your mouth for 4 seconds.\n"
            "5. Hold empty for 4 seconds.\n"
            "Repeat for 3–5 minutes."
        ),
        "target_emotions": ["fear", "anger", "surprise"],
        "target_goals": ["reduce_stress", "manage_anxiety", "manage_anger"],
        "tags": ["breath", "calm"],
    },
    {
        "slug": "physiological-sigh",
        "title": "Physiological sigh",
        "summary": "A double-inhale, long-exhale pattern to quickly reduce arousal.",
        "category": "breathing",
        "duration_seconds": 120,
        "body": (
            "1. Inhale sharply through your nose.\n"
            "2. Immediately take a second, smaller inhale on top.\n"
            "3. Slowly exhale through your mouth until your lungs feel empty.\n"
            "Repeat 3–5 times."
        ),
        "target_emotions": ["fear", "anger"],
        "target_goals": ["reduce_stress", "manage_anxiety"],
        "tags": ["breath", "quick"],
    },
    {
        "slug": "grounding-5-4-3-2-1",
        "title": "5-4-3-2-1 grounding",
        "summary": "Use your senses to return to the present moment.",
        "category": "grounding",
        "duration_seconds": 240,
        "body": (
            "Look around and name:\n"
            "• 5 things you can see\n"
            "• 4 things you can feel\n"
            "• 3 things you can hear\n"
            "• 2 things you can smell\n"
            "• 1 thing you can taste"
        ),
        "target_emotions": ["fear", "surprise", "disgust"],
        "target_goals": ["manage_anxiety", "reduce_stress"],
        "tags": ["senses", "present"],
    },
    {
        "slug": "body-scan-short",
        "title": "Short body scan",
        "summary": "Notice sensations from head to toe without changing them.",
        "category": "grounding",
        "duration_seconds": 300,
        "body": (
            "Close your eyes. Bring attention to the top of your head. Slowly move down "
            "— face, shoulders, chest, belly, hands, hips, legs, feet. Notice what you feel, "
            "without judging or trying to change it."
        ),
        "target_emotions": ["sadness", "fear"],
        "target_goals": ["reduce_stress", "sleep_better"],
        "tags": ["mindfulness"],
    },
    {
        "slug": "gratitude-three",
        "title": "Three gratitudes",
        "summary": "Name three specific things you appreciate today.",
        "category": "reflection",
        "duration_seconds": 180,
        "body": (
            "Write or say aloud three specific things you appreciate today, and why each "
            "one matters to you. Specificity matters more than novelty."
        ),
        "target_emotions": ["sadness", "neutral"],
        "target_goals": ["lift_mood", "general_wellbeing"],
        "tags": ["gratitude"],
    },
    {
        "slug": "self-compassion-break",
        "title": "Self-compassion break",
        "summary": "Acknowledge the difficulty and offer yourself kindness.",
        "category": "reflection",
        "duration_seconds": 180,
        "body": (
            "Place a hand on your chest. Silently say:\n"
            "• 'This is a moment of struggle.'\n"
            "• 'Struggle is part of being human.'\n"
            "• 'May I be kind to myself right now.'"
        ),
        "target_emotions": ["sadness", "anger", "fear"],
        "target_goals": ["lift_mood", "general_wellbeing"],
        "tags": ["self-kindness"],
    },
    {
        "slug": "name-it-to-tame-it",
        "title": "Name the feeling",
        "summary": "Label the emotion you're noticing to reduce its intensity.",
        "category": "reflection",
        "duration_seconds": 120,
        "body": (
            "Ask: 'What am I feeling, exactly? Where do I feel it in my body?' Try to "
            "pick a specific word (e.g. 'irritated' vs 'bad'). Simply naming an emotion "
            "often softens it."
        ),
        "target_emotions": ["anger", "sadness", "fear", "disgust"],
        "target_goals": ["manage_anger", "manage_anxiety"],
        "tags": ["labelling"],
    },
    {
        "slug": "gentle-stretch-2min",
        "title": "Gentle 2-minute stretch",
        "summary": "Release physical tension with slow, mindful movement.",
        "category": "movement",
        "duration_seconds": 120,
        "body": (
            "Stand up. Roll your shoulders back slowly. Reach overhead, then fold forward. "
            "Twist gently side to side. Move slowly enough to feel each stretch."
        ),
        "target_emotions": ["anger", "sadness"],
        "target_goals": ["reduce_stress", "general_wellbeing"],
        "tags": ["body"],
    },
    {
        "slug": "walk-outside-5min",
        "title": "5-minute walk outside",
        "summary": "Short walk to shift context and energy.",
        "category": "movement",
        "duration_seconds": 300,
        "body": (
            "Step outside if you can. Walk at a comfortable pace for five minutes. Notice "
            "the air, sounds, and colors around you."
        ),
        "target_emotions": ["sadness", "neutral"],
        "target_goals": ["lift_mood", "general_wellbeing"],
        "tags": ["outdoors"],
    },
    {
        "slug": "wind-down-routine",
        "title": "3-minute wind-down",
        "summary": "Prepare mind and body for rest.",
        "category": "breathing",
        "duration_seconds": 180,
        "body": (
            "Dim the lights. Breathe in for 4 seconds, exhale for 8 seconds. Let each "
            "exhale be a little longer than the inhale."
        ),
        "target_emotions": ["fear", "neutral"],
        "target_goals": ["sleep_better", "reduce_stress"],
        "tags": ["evening", "sleep"],
    },
]


async def ensure_seed(db: AsyncSession) -> int:
    """Idempotent upsert of the seed catalog. Returns number of new rows."""
    inserted = 0
    for entry in SEED_EXERCISES:
        existing = await db.execute(
            select(WellnessExercise).where(WellnessExercise.slug == entry["slug"])
        )
        if existing.scalar_one_or_none() is not None:
            continue
        db.add(WellnessExercise(**entry))
        inserted += 1
    if inserted:
        await db.commit()
    return inserted


# ---------- listing / lookup ----------


async def list_exercises(
    db: AsyncSession,
    *,
    category: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[WellnessExercise]:
    stmt = select(WellnessExercise)
    if category:
        stmt = stmt.where(WellnessExercise.category == category)
    rows = list((await db.execute(stmt.order_by(WellnessExercise.title))).scalars().all())
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    return rows


async def get_exercise_by_slug(
    db: AsyncSession, *, slug: str
) -> Optional[WellnessExercise]:
    return (
        await db.execute(select(WellnessExercise).where(WellnessExercise.slug == slug))
    ).scalar_one_or_none()


# ---------- goals ----------


async def list_goals(db: AsyncSession, *, user_id: str) -> List[UserGoal]:
    stmt = select(UserGoal).where(UserGoal.user_id == user_id).order_by(UserGoal.created_at)
    return list((await db.execute(stmt)).scalars().all())


async def add_goal(db: AsyncSession, *, user_id: str, kind: str) -> UserGoal:
    existing = (
        await db.execute(
            select(UserGoal).where(UserGoal.user_id == user_id, UserGoal.kind == kind)
        )
    ).scalar_one_or_none()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            await db.commit()
            await db.refresh(existing)
        return existing
    goal = UserGoal(user_id=user_id, kind=kind, is_active=True)
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


async def remove_goal(db: AsyncSession, *, user_id: str, goal_id: str) -> bool:
    row = (
        await db.execute(
            select(UserGoal).where(UserGoal.user_id == user_id, UserGoal.id == goal_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


# ---------- sessions ----------


async def start_session(
    db: AsyncSession, *, user_id: str, exercise_slug: str
) -> Optional[ExerciseSession]:
    ex = await get_exercise_by_slug(db, slug=exercise_slug)
    if ex is None:
        return None
    row = ExerciseSession(user_id=user_id, exercise_id=ex.id)
    db.add(row)
    await db.commit()
    # Re-fetch with the exercise eagerly loaded for response shape.
    return await get_session(db, user_id=user_id, session_id=row.id)


async def get_session(
    db: AsyncSession, *, user_id: str, session_id: str
) -> Optional[ExerciseSession]:
    stmt = (
        select(ExerciseSession)
        .options(selectinload(ExerciseSession.exercise))
        .where(ExerciseSession.id == session_id, ExerciseSession.user_id == user_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_session(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    completed: Optional[bool] = None,
    rating: Optional[int] = None,
    notes: Optional[str] = None,
) -> Optional[ExerciseSession]:
    row = await get_session(db, user_id=user_id, session_id=session_id)
    if row is None:
        return None
    if completed:
        row.completed_at = datetime.now(timezone.utc)
    if rating is not None:
        row.rating = rating
    if notes is not None:
        row.notes = notes
    await db.commit()
    return await get_session(db, user_id=user_id, session_id=session_id)


async def list_sessions(
    db: AsyncSession, *, user_id: str, limit: int = 50
) -> List[ExerciseSession]:
    stmt = (
        select(ExerciseSession)
        .options(selectinload(ExerciseSession.exercise))
        .where(ExerciseSession.user_id == user_id)
        .order_by(desc(ExerciseSession.started_at))
        .limit(min(max(1, limit), 200))
    )
    return list((await db.execute(stmt)).scalars().all())


# ---------- recommendation engine ----------


@dataclass
class ScoredExercise:
    exercise: WellnessExercise
    score: float
    reasons: List[str]


_GOAL_TO_CATEGORY = {
    "reduce_stress": "breathing",
    "manage_anxiety": "grounding",
    "manage_anger": "breathing",
    "lift_mood": "reflection",
    "sleep_better": "breathing",
    "general_wellbeing": "reflection",
}


async def _recent_dominant_emotion(
    db: AsyncSession, *, user_id: str, hours: int = 24
) -> Optional[str]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(EmotionEvent.dominant_emotion, EmotionEvent.created_at)
        .where(EmotionEvent.user_id == user_id, EmotionEvent.created_at >= since)
        .order_by(desc(EmotionEvent.created_at))
        .limit(20)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None
    counts: dict[str, float] = {}
    for i, (emo, _ts) in enumerate(rows):
        counts[emo] = counts.get(emo, 0.0) + (1.0 / (1 + i * 0.15))
    return max(counts, key=lambda k: counts[k])


async def _recent_completions(
    db: AsyncSession, *, user_id: str, hours: int = 24
) -> dict[str, ExerciseSession]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(ExerciseSession)
        .options(selectinload(ExerciseSession.exercise))
        .where(
            ExerciseSession.user_id == user_id,
            ExerciseSession.started_at >= since,
        )
    )
    rows = list((await db.execute(stmt)).scalars().all())
    by_slug: dict[str, ExerciseSession] = {}
    for r in rows:
        by_slug[r.exercise.slug] = r
    return by_slug


def _score(
    ex: WellnessExercise,
    *,
    recent_emotion: Optional[str],
    active_goals: Iterable[str],
    recently_used: bool,
    past_avg_rating: Optional[float],
) -> ScoredExercise:
    score = 0.1
    reasons: list[str] = []

    if recent_emotion and recent_emotion in (ex.target_emotions or []):
        score += 2.0
        reasons.append(f"matches recent {recent_emotion}")

    goal_bonus = 0.0
    for g in active_goals:
        if g in (ex.target_goals or []):
            goal_bonus += 1.2
            reasons.append(f"supports goal: {g}")
        if _GOAL_TO_CATEGORY.get(g) == ex.category:
            goal_bonus += 0.3
    score += goal_bonus

    if recently_used:
        score -= 0.6
        reasons.append("used recently — freshening picks")

    if past_avg_rating is not None:
        score += 0.4 * (past_avg_rating - 3.0)
        if past_avg_rating >= 4:
            reasons.append(f"you've rated this highly ({past_avg_rating:.1f}/5)")

    return ScoredExercise(exercise=ex, score=round(score, 3), reasons=reasons)


async def recommend(
    db: AsyncSession, *, user_id: str, limit: int = 5
) -> tuple[List[ScoredExercise], Optional[str], List[str]]:
    exercises = list(
        (await db.execute(select(WellnessExercise))).scalars().all()
    )
    if not exercises:
        return [], None, []

    recent_emotion = await _recent_dominant_emotion(db, user_id=user_id)
    goals = [g.kind for g in await list_goals(db, user_id=user_id) if g.is_active]
    recent_sessions = await _recent_completions(db, user_id=user_id)

    # Average rating per exercise slug for this user (all-time).
    rating_stmt = (
        select(ExerciseSession)
        .options(selectinload(ExerciseSession.exercise))
        .where(ExerciseSession.user_id == user_id, ExerciseSession.rating.is_not(None))
    )
    past_by_slug: dict[str, list[int]] = {}
    for s in (await db.execute(rating_stmt)).scalars().all():
        past_by_slug.setdefault(s.exercise.slug, []).append(int(s.rating or 0))

    scored: list[ScoredExercise] = []
    for ex in exercises:
        past_avg = None
        if ex.slug in past_by_slug and past_by_slug[ex.slug]:
            past_avg = sum(past_by_slug[ex.slug]) / len(past_by_slug[ex.slug])
        scored.append(
            _score(
                ex,
                recent_emotion=recent_emotion,
                active_goals=goals,
                recently_used=ex.slug in recent_sessions,
                past_avg_rating=past_avg,
            )
        )

    scored.sort(key=lambda s: (-s.score, s.exercise.title))
    return scored[: min(max(1, limit), 20)], recent_emotion, goals


_ = EXERCISE_CATEGORIES  # keeps the tuple accessible for validators
