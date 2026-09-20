from __future__ import annotations

import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.schemas.wellness import (
    ExerciseRead,
    ExerciseSummary,
    GoalCreate,
    GoalRead,
    Recommendation,
    RecommendationList,
    SessionCreate,
    SessionRead,
    SessionUpdate,
)
from app.services import wellness_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/wellness", tags=["wellness"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _session_read(row) -> SessionRead:
    return SessionRead(
        id=row.id,
        exercise_id=row.exercise_id,
        exercise_slug=row.exercise.slug,
        exercise_title=row.exercise.title,
        started_at=row.started_at,
        completed_at=row.completed_at,
        rating=row.rating,
        notes=row.notes,
    )


@router.get("/exercises", response_model=List[ExerciseRead])
async def list_exercises(
    _user: CurrentUser,
    db: DbDep,
    category: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> List[ExerciseRead]:
    rows = await wellness_service.list_exercises(db, category=category, tag=tag)
    return [ExerciseRead.model_validate(r) for r in rows]


@router.get("/exercises/{slug}", response_model=ExerciseRead)
async def get_exercise(
    slug: str,
    _user: CurrentUser,
    db: DbDep,
) -> ExerciseRead:
    row = await wellness_service.get_exercise_by_slug(db, slug=slug)
    if row is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return ExerciseRead.model_validate(row)


@router.get("/recommendations", response_model=RecommendationList)
async def recommendations(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=5, ge=1, le=20),
) -> RecommendationList:
    scored, recent_emotion, goals = await wellness_service.recommend(
        db, user_id=user.id, limit=limit
    )
    return RecommendationList(
        items=[
            Recommendation(
                exercise=ExerciseSummary.model_validate(s.exercise),
                score=s.score,
                reasons=s.reasons,
            )
            for s in scored
        ],
        recent_dominant_emotion=recent_emotion,
        active_goals=goals,
    )


@router.post("/sessions", response_model=SessionRead, status_code=201)
async def start_session(
    body: SessionCreate,
    user: CurrentUser,
    db: DbDep,
) -> SessionRead:
    row = await wellness_service.start_session(
        db, user_id=user.id, exercise_slug=body.exercise_slug
    )
    if row is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return _session_read(row)


@router.patch("/sessions/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: str,
    body: SessionUpdate,
    user: CurrentUser,
    db: DbDep,
) -> SessionRead:
    row = await wellness_service.update_session(
        db,
        user_id=user.id,
        session_id=session_id,
        completed=body.completed,
        rating=body.rating,
        notes=body.notes,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_read(row)


@router.get("/sessions", response_model=List[SessionRead])
async def list_sessions(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> List[SessionRead]:
    rows = await wellness_service.list_sessions(db, user_id=user.id, limit=limit)
    return [_session_read(r) for r in rows]


@router.get("/goals", response_model=List[GoalRead])
async def list_goals(user: CurrentUser, db: DbDep) -> List[GoalRead]:
    rows = await wellness_service.list_goals(db, user_id=user.id)
    return [GoalRead.model_validate(r) for r in rows]


@router.post("/goals", response_model=GoalRead, status_code=201)
async def add_goal(
    body: GoalCreate, user: CurrentUser, db: DbDep
) -> GoalRead:
    row = await wellness_service.add_goal(db, user_id=user.id, kind=body.kind)
    return GoalRead.model_validate(row)


@router.delete("/goals/{goal_id}", status_code=204)
async def remove_goal(
    goal_id: str, user: CurrentUser, db: DbDep
) -> None:
    ok = await wellness_service.remove_goal(db, user_id=user.id, goal_id=goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="goal not found")
