"""Reminders worker entry point (Phase 9 + Phase 14).

Runs the same dispatcher loop that ``app.main`` starts inside the FastAPI
lifespan, but as a standalone process so a restart of the web tier does not
miss reminder ticks. Deployed as a Render ``worker`` service (see
``render.yaml``).

Phase 15 P1 §5.6 adds a second loop that purges expired refresh tokens,
old notifications, and old audit events on a daily cadence.
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db import session as _session_mod
from app.services import reminders_service, retention_service, task_queue

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
log = logging.getLogger("app.worker")


async def _loop(interval_seconds: float) -> None:
    while True:
        try:
            async with _session_mod.SessionLocal() as db:
                created = await reminders_service.dispatch_due(db)
                delivered = await reminders_service.deliver_pending_email_notifications(db)
                pushed = await reminders_service.deliver_pending_push_notifications(db)
                jobs = await task_queue.process_pending(db)
                if created:
                    log.info("reminders: dispatched %d notifications", created)
                if delivered:
                    log.info("reminders: delivered %d emails", delivered)
                if pushed:
                    log.info("reminders: delivered %d push notifications", pushed)
                if jobs:
                    log.info("tasks: completed %d durable jobs", jobs)
        except Exception as e:  # noqa: BLE001
            log.warning("reminders: dispatch failed (%s)", e)
        await asyncio.sleep(interval_seconds)


async def _retention_loop(interval_seconds: float) -> None:
    while True:
        try:
            async with _session_mod.SessionLocal() as db:
                await retention_service.purge_once(
                    db,
                    audit_days=settings.retention_audit_days,
                    notification_days=settings.retention_notification_days,
                )
        except Exception as e:  # noqa: BLE001
            log.warning("retention: purge failed (%s)", e)
        await asyncio.sleep(interval_seconds)


async def _main() -> None:
    tasks = [asyncio.create_task(_loop(settings.reminders_scheduler_interval_seconds))]
    if settings.retention_purge_enabled:
        tasks.append(
            asyncio.create_task(
                _retention_loop(settings.retention_purge_interval_seconds)
            )
        )
        log.info(
            "retention: enabled (every %.1fs, audit=%dd, notif=%dd)",
            settings.retention_purge_interval_seconds,
            settings.retention_audit_days,
            settings.retention_notification_days,
        )
    await asyncio.gather(*tasks)


def main() -> None:
    interval = settings.reminders_scheduler_interval_seconds
    log.info("worker starting (interval=%.1fs, env=%s)", interval, settings.app_env)
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("worker stopped")


if __name__ == "__main__":
    main()
