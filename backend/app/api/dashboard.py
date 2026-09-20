"""Dashboard read-only API (plan §10)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.schemas.dashboard import (
    DashboardInsights,
    DashboardSummary,
    DashboardTrends,
    EmotionsBreakdown,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    user: CurrentUser,
    db: DbDep,
    window_days: int = Query(7, ge=1, le=90),
) -> DashboardSummary:
    data = await dashboard_service.build_summary(
        db, user_id=user.id, window_days=window_days
    )
    return DashboardSummary.model_validate(data)


@router.get("/emotions", response_model=EmotionsBreakdown)
async def emotions(
    user: CurrentUser,
    db: DbDep,
    window_days: int = Query(30, ge=1, le=90),
) -> EmotionsBreakdown:
    data = await dashboard_service.build_emotions(
        db, user_id=user.id, window_days=window_days
    )
    return EmotionsBreakdown.model_validate(data)


@router.get("/trends", response_model=DashboardTrends)
async def trends(
    user: CurrentUser,
    db: DbDep,
    window_days: int = Query(30, ge=1, le=90),
) -> DashboardTrends:
    data = await dashboard_service.build_trends(
        db, user_id=user.id, window_days=window_days
    )
    return DashboardTrends.model_validate(data)


@router.get("/insights", response_model=DashboardInsights)
async def insights(
    user: CurrentUser,
    db: DbDep,
    window_days: int = Query(7, ge=1, le=90),
) -> DashboardInsights:
    data = await dashboard_service.build_insights(
        db, user_id=user.id, window_days=window_days
    )
    return DashboardInsights.model_validate(data)
