from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    display_name: Optional[str] = None
    timezone: str = "UTC"
    age_confirmed: bool = False
    dob_year: Optional[int] = None


class UserPreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notification_email: bool = True
    theme: str = "system"
    memory_enabled: bool = True
    mic_consent: bool = False
    camera_consent: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    mfa_enabled: bool = False
    created_at: datetime
    profile: Optional[UserProfileOut] = None
    preferences: Optional[UserPreferencesOut] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=64)
    age_confirmed: Optional[bool] = None
    dob_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    notification_email: Optional[bool] = None
    theme: Optional[str] = Field(default=None, pattern=r"^(system|light|dark)$")
    memory_enabled: Optional[bool] = None
    mic_consent: Optional[bool] = None
    camera_consent: Optional[bool] = None
