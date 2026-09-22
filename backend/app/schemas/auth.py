from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    age_confirmed: bool = False
    dob_year: int | None = Field(default=None, ge=1900, le=2100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=100, max_length=8192)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=4096)


class SimpleMessage(BaseModel):
    detail: str


class EmailRequest(BaseModel):
    email: EmailStr


class ActionTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class PasswordResetRequest(ActionTokenRequest):
    new_password: str = Field(min_length=8, max_length=128)


class DeviceSession(BaseModel):
    family_id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    ip: str | None = None


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MFASetupRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class MFACodeRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class MFADisableRequest(MFACodeRequest):
    password: str = Field(min_length=1, max_length=128)
