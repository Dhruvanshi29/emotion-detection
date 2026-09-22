"""Therapist directory models (plan §9 + §22).

Curated professional listings — NOT user-generated content. Every profile
must carry a `therapist_verifications` row before it goes live; the platform
provides a discovery/filter tool and does not endorse individuals.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


VERIFICATION_STATUSES = ("pending", "verified", "expired", "rejected")
REPORT_KINDS = (
    "outdated_info",
    "incorrect_contact",
    "not_practicing",
    "impersonation",
    "other",
)
REPORT_STATUSES = ("open", "resolved", "dismissed")


class Therapist(Base):
    __tablename__ = "therapists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    photo_url: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)

    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    city: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    session_price_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    session_price_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    offers_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    offers_in_person: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_new_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    specializations: Mapped[List["TherapistSpecialization"]] = relationship(
        back_populates="therapist", cascade="all, delete-orphan", lazy="selectin"
    )
    languages: Mapped[List["TherapistLanguage"]] = relationship(
        back_populates="therapist", cascade="all, delete-orphan", lazy="selectin"
    )
    availability: Mapped[List["TherapistAvailability"]] = relationship(
        back_populates="therapist", cascade="all, delete-orphan", lazy="selectin"
    )
    verifications: Mapped[List["TherapistVerification"]] = relationship(
        back_populates="therapist", cascade="all, delete-orphan", lazy="selectin"
    )


class TherapistSpecialization(Base):
    __tablename__ = "therapist_specializations"
    __table_args__ = (
        UniqueConstraint("therapist_id", "value", name="uq_therapist_specialization"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    therapist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("therapists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(String(48), nullable=False)

    therapist: Mapped["Therapist"] = relationship(back_populates="specializations")


class TherapistLanguage(Base):
    __tablename__ = "therapist_languages"
    __table_args__ = (
        UniqueConstraint("therapist_id", "code", name="uq_therapist_language"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    therapist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("therapists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(8), nullable=False)

    therapist: Mapped["Therapist"] = relationship(back_populates="languages")


class TherapistAvailability(Base):
    __tablename__ = "therapist_availability"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    therapist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("therapists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon .. 6=Sun
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    therapist: Mapped["Therapist"] = relationship(back_populates="availability")


class TherapistVerification(Base):
    __tablename__ = "therapist_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    therapist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("therapists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    license_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    license_authority: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    therapist: Mapped["Therapist"] = relationship(back_populates="verifications")


class TherapistReport(Base):
    """Plan §22 reporting mechanism for outdated / incorrect professional info."""

    __tablename__ = "therapist_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    therapist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("therapists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


__all__ = [
    "VERIFICATION_STATUSES",
    "REPORT_KINDS",
    "REPORT_STATUSES",
    "Therapist",
    "TherapistSpecialization",
    "TherapistLanguage",
    "TherapistAvailability",
    "TherapistVerification",
    "TherapistReport",
]
