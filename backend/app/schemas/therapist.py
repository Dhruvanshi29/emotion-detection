from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.therapist import REPORT_KINDS, REPORT_STATUSES, VERIFICATION_STATUSES


class TherapistAvailabilitySlot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, le=24 * 60)
    end_minute: int = Field(ge=0, le=24 * 60)


class TherapistVerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    license_number: Optional[str] = None
    license_authority: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    expires_at: Optional[datetime] = None


class TherapistSummary(BaseModel):
    id: str
    slug: str
    full_name: str
    title: str
    country_code: str
    city: Optional[str] = None
    session_price_min: Optional[float] = None
    session_price_max: Optional[float] = None
    currency: str
    offers_online: bool
    offers_in_person: bool
    accepts_new_clients: bool
    specializations: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    verified: bool
    verification_status: str


class TherapistDetail(TherapistSummary):
    bio: str
    photo_url: Optional[str] = None
    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    timezone: Optional[str] = None
    availability: List[TherapistAvailabilitySlot] = Field(default_factory=list)
    verification: Optional[TherapistVerificationRead] = None
    disclaimer: str = (
        "This platform is a discovery and filter tool. It does not endorse, "
        "employ, or supervise listed professionals. Please independently verify "
        "credentials, licensing, and current practice status before contacting."
    )


class TherapistList(BaseModel):
    items: List[TherapistSummary]
    total: int
    skip: int
    limit: int


class TherapistFilters(BaseModel):
    q: Optional[str] = None
    specialization: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    modality: Optional[Literal["online", "in_person", "any"]] = None
    accepts_new_clients: Optional[bool] = None
    verified_only: bool = True
    price_max: Optional[float] = None
    price_min: Optional[float] = None
    order: Literal["default", "name", "price_asc", "price_desc"] = "default"
    skip: int = 0
    limit: int = 20


class TherapistReportCreate(BaseModel):
    kind: str
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in REPORT_KINDS:
            raise ValueError(f"unknown report kind: {v}")
        return v


class TherapistReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    therapist_id: str
    kind: str
    notes: Optional[str] = None
    status: str
    created_at: datetime


class TherapistAdminCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    full_name: str = Field(min_length=2, max_length=160)
    title: str = Field(min_length=2, max_length=120)
    bio: str = Field(min_length=10, max_length=5000)
    country_code: str = Field(min_length=2, max_length=2)
    city: Optional[str] = Field(default=None, max_length=80)
    timezone: Optional[str] = Field(default=None, max_length=64)
    session_price_min: Optional[float] = Field(default=None, ge=0)
    session_price_max: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    offers_online: bool = True
    offers_in_person: bool = False
    accepts_new_clients: bool = True
    contact_email: Optional[str] = Field(default=None, max_length=255)
    website_url: Optional[str] = Field(default=None, max_length=400)
    photo_url: Optional[str] = Field(default=None, max_length=400)
    specializations: List[str] = Field(default_factory=list, max_length=30)
    languages: List[str] = Field(default_factory=list, max_length=20)
    availability: List[TherapistAvailabilitySlot] = Field(default_factory=list, max_length=30)


class TherapistVerificationUpdate(BaseModel):
    status: str
    license_number: Optional[str] = Field(default=None, max_length=120)
    license_authority: Optional[str] = Field(default=None, max_length=200)
    expires_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in VERIFICATION_STATUSES:
            raise ValueError("invalid verification status")
        return value


class TherapistReportStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def _report_status(cls, value: str) -> str:
        if value not in REPORT_STATUSES:
            raise ValueError("invalid report status")
        return value
