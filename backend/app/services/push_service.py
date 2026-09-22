from __future__ import annotations

import asyncio
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.push_subscription import PushSubscription


def configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key and s.vapid_subject)


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


async def upsert(db: AsyncSession, *, user_id: str, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
    digest = endpoint_hash(endpoint)
    row = (await db.execute(select(PushSubscription).where(PushSubscription.endpoint_hash == digest))).scalar_one_or_none()
    if row is None:
        row = PushSubscription(user_id=user_id, endpoint=endpoint, endpoint_hash=digest, p256dh=p256dh, auth=auth)
        db.add(row)
    elif row.user_id != user_id:
        # Browser endpoints are single-account credentials.
        row.user_id = user_id
        row.endpoint = endpoint
        row.p256dh = p256dh
        row.auth = auth
    await db.commit()
    await db.refresh(row)
    return row


async def remove(db: AsyncSession, *, user_id: str, endpoint: str) -> bool:
    row = (await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id, PushSubscription.endpoint_hash == endpoint_hash(endpoint)))).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def send_user(db: AsyncSession, *, user_id: str, title: str, body: str) -> bool:
    if not configured():
        return False
    subscriptions = list((await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))).scalars().all())
    if not subscriptions:
        return False
    s = get_settings()

    def _send(subscription: PushSubscription) -> bool:
        from pywebpush import webpush

        webpush(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps({"title": title, "body": body, "url": "/reminders"}),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject},
            ttl=3600,
        )
        return True

    delivered = False
    for subscription in subscriptions:
        try:
            delivered = await asyncio.to_thread(_send, subscription) or delivered
        except Exception:
            # Delivery retries are tracked by the notification outbox; avoid
            # exposing endpoint material in logs.
            continue
    return delivered
