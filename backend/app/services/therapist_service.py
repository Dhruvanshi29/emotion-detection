"""Therapist directory service (plan §8, §22).

- Filter-only discovery (no AI ranking) per §22.
- `list_therapists` supports explicit filters and deterministic ordering.
- `ensure_seed` inserts a small curated starter directory for dev/tests.
- Every therapist profile carries the latest verification row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.therapist import (
    Therapist,
    TherapistAvailability,
    TherapistLanguage,
    TherapistReport,
    TherapistSpecialization,
    TherapistVerification,
)
from app.schemas.therapist import TherapistAdminCreate, TherapistFilters

logger = logging.getLogger(__name__)


SEED_THERAPISTS: list[dict] = [
    {
        "slug": "dr-amelia-chen",
        "full_name": "Dr. Amelia Chen",
        "title": "Licensed Clinical Psychologist, PhD",
        "bio": (
            "Amelia works with adults on anxiety, burnout, and life transitions. She "
            "integrates cognitive-behavioral therapy with mindfulness-based techniques."
        ),
        "country_code": "US",
        "city": "San Francisco",
        "timezone": "America/Los_Angeles",
        "session_price_min": 180.0,
        "session_price_max": 220.0,
        "currency": "USD",
        "offers_online": True,
        "offers_in_person": True,
        "accepts_new_clients": True,
        "contact_email": "hello@ameliachen.example",
        "website_url": "https://ameliachen.example",
        "specializations": ["anxiety", "burnout", "life_transitions", "cbt"],
        "languages": ["en", "zh"],
        "availability": [(0, 9, 17), (2, 9, 17), (4, 9, 13)],
        "verification": {
            "status": "verified",
            "license_number": "PSY-8811",
            "license_authority": "California Board of Psychology",
            "verified_by": "staff-01",
        },
    },
    {
        "slug": "raj-patel-lmft",
        "full_name": "Raj Patel, LMFT",
        "title": "Licensed Marriage and Family Therapist",
        "bio": "Raj focuses on couples, family systems, and cross-cultural identity work.",
        "country_code": "US",
        "city": "Austin",
        "timezone": "America/Chicago",
        "session_price_min": 140.0,
        "session_price_max": 170.0,
        "currency": "USD",
        "offers_online": True,
        "offers_in_person": True,
        "accepts_new_clients": True,
        "specializations": ["couples", "family_systems", "identity"],
        "languages": ["en", "hi", "gu"],
        "availability": [(1, 10, 18), (3, 10, 18)],
        "verification": {
            "status": "verified",
            "license_number": "LMFT-44921",
            "license_authority": "Texas State Board of Examiners of MFTs",
            "verified_by": "staff-02",
        },
    },
    {
        "slug": "sofia-alvarez",
        "full_name": "Sofía Álvarez",
        "title": "Clinical Social Worker, LCSW",
        "bio": (
            "Sofía offers bilingual therapy in English and Spanish, with a focus on "
            "trauma-informed care, grief, and immigration-related stress."
        ),
        "country_code": "US",
        "city": "New York",
        "timezone": "America/New_York",
        "session_price_min": 120.0,
        "session_price_max": 150.0,
        "currency": "USD",
        "offers_online": True,
        "offers_in_person": False,
        "accepts_new_clients": False,
        "specializations": ["trauma", "grief", "acculturation"],
        "languages": ["en", "es"],
        "availability": [(0, 12, 20), (2, 12, 20), (4, 12, 20)],
        "verification": {
            "status": "verified",
            "license_number": "LCSW-77102",
            "license_authority": "NY State Education Department",
            "verified_by": "staff-01",
        },
    },
    {
        "slug": "priya-shah-online",
        "full_name": "Priya Shah",
        "title": "Counselling Psychologist",
        "bio": "Priya sees young adults dealing with academic stress, relationships, and self-esteem.",
        "country_code": "IN",
        "city": "Mumbai",
        "timezone": "Asia/Kolkata",
        "session_price_min": 2500.0,
        "session_price_max": 3500.0,
        "currency": "INR",
        "offers_online": True,
        "offers_in_person": True,
        "accepts_new_clients": True,
        "specializations": ["anxiety", "young_adults", "self_esteem"],
        "languages": ["en", "hi", "mr"],
        "availability": [(0, 16, 21), (2, 16, 21), (5, 10, 14)],
        "verification": {
            "status": "verified",
            "license_number": "RCI-CP-33021",
            "license_authority": "Rehabilitation Council of India",
            "verified_by": "staff-03",
        },
    },
    {
        "slug": "james-oconnor",
        "full_name": "James O'Connor",
        "title": "Psychotherapist, MSc",
        "bio": "James works with men on anger regulation, addiction recovery, and grief.",
        "country_code": "GB",
        "city": "London",
        "timezone": "Europe/London",
        "session_price_min": 90.0,
        "session_price_max": 120.0,
        "currency": "GBP",
        "offers_online": True,
        "offers_in_person": True,
        "accepts_new_clients": True,
        "specializations": ["anger", "addiction", "grief", "men"],
        "languages": ["en"],
        "availability": [(1, 9, 17), (3, 9, 17)],
        "verification": {
            "status": "verified",
            "license_number": "BACP-88112",
            "license_authority": "BACP",
            "verified_by": "staff-02",
        },
    },
    {
        "slug": "nadia-almeida-pending",
        "full_name": "Nadia Almeida",
        "title": "Clinical Psychologist (verification in progress)",
        "bio": "Verification pending — profile not yet publicly listed.",
        "country_code": "PT",
        "city": "Lisbon",
        "timezone": "Europe/Lisbon",
        "session_price_min": 60.0,
        "session_price_max": 80.0,
        "currency": "EUR",
        "offers_online": True,
        "offers_in_person": False,
        "accepts_new_clients": True,
        "specializations": ["anxiety", "depression"],
        "languages": ["en", "pt"],
        "availability": [(0, 9, 15)],
        "verification": {
            "status": "pending",
            "license_number": None,
            "license_authority": "Ordem dos Psicólogos Portugueses",
            "verified_by": None,
        },
    },
]


async def ensure_seed(db: AsyncSession) -> int:
    inserted = 0
    for source in SEED_THERAPISTS:
        # The seed constants are shared across lifespan/test invocations.
        # Copy nested values before popping so repeated startup stays safe.
        entry = dict(source)
        row = (
            await db.execute(select(Therapist).where(Therapist.slug == entry["slug"]))
        ).scalar_one_or_none()
        if row is not None:
            continue
        specs = entry.pop("specializations", [])
        langs = entry.pop("languages", [])
        avail = entry.pop("availability", [])
        verification = entry.pop("verification", None)

        row = Therapist(**entry)
        db.add(row)
        await db.flush()

        for s in specs:
            db.add(TherapistSpecialization(therapist_id=row.id, value=s))
        for lg in langs:
            db.add(TherapistLanguage(therapist_id=row.id, code=lg))
        for wd, sh, eh in avail:
            db.add(
                TherapistAvailability(
                    therapist_id=row.id,
                    weekday=wd,
                    start_minute=sh * 60,
                    end_minute=eh * 60,
                )
            )
        if verification is not None:
            verified_at = None
            expires_at = None
            if verification.get("status") == "verified":
                verified_at = datetime.now(timezone.utc)
                expires_at = verified_at + timedelta(days=365)
            db.add(
                TherapistVerification(
                    therapist_id=row.id,
                    status=verification.get("status", "pending"),
                    license_number=verification.get("license_number"),
                    license_authority=verification.get("license_authority"),
                    verified_at=verified_at,
                    verified_by=verification.get("verified_by"),
                    expires_at=expires_at,
                )
            )
        inserted += 1
    if inserted:
        await db.commit()
    return inserted


def latest_verification(t: Therapist) -> Optional[TherapistVerification]:
    if not t.verifications:
        return None
    return sorted(t.verifications, key=lambda v: v.created_at, reverse=True)[0]


def is_verified(t: Therapist) -> bool:
    v = latest_verification(t)
    if v is None:
        return False
    if v.status != "verified":
        return False
    if v.expires_at is not None:
        exp = v.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return False
    return True


async def list_therapists(
    db: AsyncSession, *, filters: TherapistFilters
) -> tuple[List[Therapist], int]:
    stmt = (
        select(Therapist)
        .where(Therapist.is_active.is_(True))
        .options(
            selectinload(Therapist.specializations),
            selectinload(Therapist.languages),
            selectinload(Therapist.verifications),
        )
    )

    if filters.q:
        needle = f"%{filters.q.strip()}%"
        stmt = stmt.where(
            or_(Therapist.full_name.ilike(needle), Therapist.title.ilike(needle))
        )
    if filters.country:
        stmt = stmt.where(Therapist.country_code == filters.country.upper())
    if filters.city:
        stmt = stmt.where(Therapist.city.ilike(f"%{filters.city}%"))
    if filters.modality == "online":
        stmt = stmt.where(Therapist.offers_online.is_(True))
    elif filters.modality == "in_person":
        stmt = stmt.where(Therapist.offers_in_person.is_(True))
    if filters.accepts_new_clients is not None:
        stmt = stmt.where(Therapist.accepts_new_clients.is_(filters.accepts_new_clients))
    if filters.price_max is not None:
        stmt = stmt.where(
            or_(
                Therapist.session_price_min.is_(None),
                Therapist.session_price_min <= filters.price_max,
            )
        )
    if filters.price_min is not None:
        stmt = stmt.where(
            or_(
                Therapist.session_price_max.is_(None),
                Therapist.session_price_max >= filters.price_min,
            )
        )
    if filters.specialization:
        sub = (
            select(TherapistSpecialization.therapist_id)
            .where(TherapistSpecialization.value == filters.specialization)
            .subquery()
        )
        stmt = stmt.where(Therapist.id.in_(select(sub.c.therapist_id)))
    if filters.language:
        sub = (
            select(TherapistLanguage.therapist_id)
            .where(TherapistLanguage.code == filters.language)
            .subquery()
        )
        stmt = stmt.where(Therapist.id.in_(select(sub.c.therapist_id)))

    # Default: verified first, then accepts_new_clients, then name.
    if filters.order == "name":
        stmt = stmt.order_by(asc(Therapist.full_name))
    elif filters.order == "price_asc":
        stmt = stmt.order_by(asc(Therapist.session_price_min))
    elif filters.order == "price_desc":
        stmt = stmt.order_by(desc(Therapist.session_price_max))
    else:
        stmt = stmt.order_by(
            desc(Therapist.accepts_new_clients),
            asc(Therapist.full_name),
        )

    all_rows = list((await db.execute(stmt)).unique().scalars().all())

    if filters.verified_only:
        all_rows = [r for r in all_rows if is_verified(r)]

    total = len(all_rows)
    skip = max(0, filters.skip)
    limit = max(1, min(200, filters.limit))
    return all_rows[skip : skip + limit], total


async def get_therapist_by_slug(
    db: AsyncSession, *, slug: str
) -> Optional[Therapist]:
    stmt = (
        select(Therapist)
        .where(Therapist.slug == slug, Therapist.is_active.is_(True))
        .options(
            selectinload(Therapist.specializations),
            selectinload(Therapist.languages),
            selectinload(Therapist.availability),
            selectinload(Therapist.verifications),
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_report(
    db: AsyncSession, *, user_id: str, therapist_id: str, kind: str, notes: Optional[str]
) -> TherapistReport:
    row = TherapistReport(
        user_id=user_id, therapist_id=therapist_id, kind=kind, notes=notes
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def count_reports(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(TherapistReport))).scalar_one())


async def admin_create_therapist(db: AsyncSession, payload: TherapistAdminCreate) -> Therapist:
    data = payload.model_dump(exclude={"specializations", "languages", "availability"})
    data["country_code"] = payload.country_code.upper()
    data["currency"] = payload.currency.upper()
    row = Therapist(**data)
    db.add(row)
    await db.flush()
    for value in payload.specializations:
        db.add(TherapistSpecialization(therapist_id=row.id, value=value.strip().lower()))
    for code in payload.languages:
        db.add(TherapistLanguage(therapist_id=row.id, code=code.strip().lower()))
    for slot in payload.availability:
        db.add(TherapistAvailability(therapist_id=row.id, **slot.model_dump()))
    db.add(TherapistVerification(therapist_id=row.id, status="pending"))
    await db.commit()
    loaded = await get_therapist_by_slug(db, slug=row.slug)
    assert loaded is not None
    return loaded


# Re-export names touched via and_/func for linters.
_ = (and_, func)
