from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from nexus_core.config import get_settings
from nexus_core.logging import configure_logging, get_logger

logger = get_logger(__name__)
settings = get_settings()


async def _poll_connections() -> None:
    logger.info("scheduler.poll_connections_tick")


async def _renew_webhooks() -> None:
    logger.info("scheduler.renew_webhooks_tick")


async def main() -> None:
    configure_logging()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_poll_connections, "interval", minutes=15, id="poll_connections")
    scheduler.add_job(_renew_webhooks, "interval", minutes=30, id="renew_webhooks")
    scheduler.start()

    logger.info("scheduler.started", environment=settings.environment)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
