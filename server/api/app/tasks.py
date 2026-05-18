"""
Фоновые задачи приложения.

Использует APScheduler для периодических задач.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import update

from app.database import async_session_factory
from app.models import Robot, RobotStatus

logger = logging.getLogger(__name__)

INACTIVITY_THRESHOLD_SECONDS = 60
CHECK_INTERVAL_SECONDS = 30

scheduler = AsyncIOScheduler()


async def mark_inactive_robots() -> None:
    """Помечает роботов как неактивных если метрики не приходили дольше порога."""
    threshold = datetime.now(UTC) - timedelta(seconds=INACTIVITY_THRESHOLD_SECONDS)

    async with async_session_factory() as session:
        result = await session.execute(
            update(Robot)
            .where(
                Robot.status == RobotStatus.ACTIVE,
                Robot.last_seen_at < threshold,
            )
            .values(status=RobotStatus.INACTIVE)
            .returning(Robot.id, Robot.name)
        )
        updated = result.fetchall()

        if updated:
            await session.commit()
            for robot_id, robot_name in updated:
                logger.info("Robot marked inactive: id=%d name=%s", robot_id, robot_name)


def start_scheduler() -> None:
    """Запускает планировщик задач."""
    scheduler.add_job(
        mark_inactive_robots,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        id="mark_inactive_robots",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: checking robot activity every %ds, threshold %ds",
        CHECK_INTERVAL_SECONDS,
        INACTIVITY_THRESHOLD_SECONDS,
    )


def stop_scheduler() -> None:
    """Останавливает планировщик задач."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
