from __future__ import annotations

import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.therapist import Therapist, TherapistVerification
from app.schemas.therapist import (
    TherapistAvailabilitySlot,
    TherapistDetail,
    TherapistFilters,
    TherapistList,
    TherapistReportCreate,
    TherapistReportRead,
    TherapistSummary,
    TherapistVerificationRead,
)
from app.services import therapist_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/therapists", tags=["therapists"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _summary(t: Therapist) -> TherapistSummary:
    v = therapist_service.latest_verification(t)
    return TherapistSummary(
        id=t.id,
        slug=t.slug,
        full_name=t.full_name,
        title=t.title,
        country_code=t.country_code,
        city=t.city,
        session_price_min=t.session_price_min,
        session_price_max=t.session_price_max,
        currency=t.currency,
        offers_online=t.offers_online,
        offers_in_person=t.offers_in_person,
        accepts_new_clients=t.accepts_new_clients,
        specializations=[s.value for s in t.specializations],
        languages=[lg.code for lg in t.languages],
        verified=therapist_service.is_verified(t),
        verification_status=v.status if v else "unverified",
    )


def _detail(t: Therapist) -> TherapistDetail:
    base = _summary(t)
    v: Optional[TherapistVerification] = therapist_service.latest_verification(t)
    return TherapistDetail(
        **base.model_dump(),
        bio=t.bio,
        photo_url=t.photo_url,
        website_url=t.website_url,
        contact_email=t.contact_email,
        timezone=t.timezone,
        availability=[
            TherapistAvailabilitySlot.model_validate(a) for a in t.availability
        ],
        verification=TherapistVerificationRead.model_validate(v) if v else None,
    )


@router.get("", response_model=TherapistList)
async def list_therapists(
    _user: CurrentUser,
    db: DbDep,
    q: Optional[str] = Query(default=None),
    specialization: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None, min_length=2, max_length=2),
    city: Optional[str] = Query(default=None),
    modality: Optional[str] = Query(default=None),
    accepts_new_clients: Optional[bool] = Query(default=None),
    verified_only: bool = Query(default=True),
    price_min: Optional[float] = Query(default=None, ge=0),
    price_max: Optional[float] = Query(default=None, ge=0),
    order: str = Query(default="default"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> TherapistList:
    try:
        filters = TherapistFilters(
            q=q,
            specialization=specialization,
            language=language,
            country=country,
            city=city,
            modality=modality,  # type: ignore[arg-type]
            accepts_new_clients=accepts_new_clients,
            verified_only=verified_only,
            price_min=price_min,
            price_max=price_max,
            order=order,  # type: ignore[arg-type]
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    rows, total = await therapist_service.list_therapists(db, filters=filters)
    return TherapistList(
        items=[_summary(r) for r in rows],
        total=total,
        skip=filters.skip,
        limit=filters.limit,
    )


@router.get("/{slug}", response_model=TherapistDetail)
async def get_therapist(
    slug: str,
    _user: CurrentUser,
    db: DbDep,
) -> TherapistDetail:
    row = await therapist_service.get_therapist_by_slug(db, slug=slug)
    if row is None:
        raise HTTPException(status_code=404, detail="therapist not found")
    # Never expose an unverified profile publicly (plan §22).
    if not therapist_service.is_verified(row):
        raise HTTPException(status_code=404, detail="therapist not found")
    return _detail(row)


@router.post(
    "/{slug}/report", response_model=TherapistReportRead, status_code=201
)
async def report_therapist(
    slug: str,
    body: TherapistReportCreate,
    user: CurrentUser,
    db: DbDep,
) -> TherapistReportRead:
    row = await therapist_service.get_therapist_by_slug(db, slug=slug)
    if row is None:
        raise HTTPException(status_code=404, detail="therapist not found")
    report = await therapist_service.create_report(
        db,
        user_id=user.id,
        therapist_id=row.id,
        kind=body.kind,
        notes=body.notes,
    )
    return TherapistReportRead.model_validate(report)
