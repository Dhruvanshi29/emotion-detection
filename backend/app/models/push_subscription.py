from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedText
from app.db.base import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    auth: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
