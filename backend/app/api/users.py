from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.user import User, UserPreferences, UserProfile
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


_PROFILE_FIELDS = {"display_name", "timezone", "age_confirmed", "dob_year"}
_PREF_FIELDS = {
    "notification_email",
    "theme",
    "memory_enabled",
    "mic_consent",
    "camera_consent",
}


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def patch_me(
    update: UserUpdate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    data = update.model_dump(exclude_unset=True)

    if user.profile is None:
        user.profile = UserProfile()
    if user.preferences is None:
        user.preferences = UserPreferences()

    for key, value in data.items():
        if key in _PROFILE_FIELDS:
            setattr(user.profile, key, value)
        elif key in _PREF_FIELDS:
            setattr(user.preferences, key, value)

    db.add(user)
    await db.commit()
    await db.refresh(user, attribute_names=["profile", "preferences"])
    return user
