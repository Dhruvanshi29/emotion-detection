"""Consent, audit, and privacy schemas (plan §12, §13)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.audit import CONSENT_KINDS, CONSENT_SOURCES


# ---------- Consent ----------


class ConsentUpdate(BaseModel):
    kind: str
    granted: bool
    source: str = "settings"
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in CONSENT_KINDS:
            raise ValueError(f"kind must be one of {CONSENT_KINDS}")
        return v

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in CONSENT_SOURCES:
            raise ValueError(f"source must be one of {CONSENT_SOURCES}")
        return v


class ConsentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    granted: bool
    source: str
    notes: Optional[str] = None
    created_at: datetime


class ConsentState(BaseModel):
    # Current values pulled from UserPreferences.
    mic: bool
    camera: bool
    memory: bool
    # Terms + data_processing default False until explicitly recorded via /consent.
    data_processing: bool
    terms: bool
    history: List[ConsentEventOut]


# ---------- Audit ----------


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    action: str
    details: Optional[Any] = None
    created_at: datetime


class AuditList(BaseModel):
    items: List[AuditEventOut]
    total: int


# ---------- Privacy: export + deletion ----------


PRIVACY_CATEGORIES = (
    "chat",
    "journal",
    "emotion",
    "voice",
    "facial",
    "wellness",
    "reminders",
    "memory",
    "audit",
)


class CategoryDelete(BaseModel):
    category: Literal[
        "chat",
        "journal",
        "emotion",
        "voice",
        "facial",
        "wellness",
        "reminders",
        "memory",
        "audit",
    ]


class CategoryDeleteResult(BaseModel):
    category: str
    deleted: int


class DeleteAccountRequest(BaseModel):
    # Simple guard against accidental clicks — client passes the literal string.
    confirm: str

    @field_validator("confirm")
    @classmethod
    def _confirm(cls, v: str) -> str:
        if v.strip().upper() != "DELETE":
            raise ValueError('confirm must be "DELETE"')
        return v


class DeleteAccountResult(BaseModel):
    user_id: str
    deleted_at: datetime
    counts: Dict[str, int]


class DataExport(BaseModel):
    # Free-form dump; shape is documented in privacy_service.export_user_data.
    generated_at: datetime
    user: Dict[str, Any]
    counts: Dict[str, int]
    data: Dict[str, Any]
