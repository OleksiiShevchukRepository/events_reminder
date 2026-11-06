"""Daily cleanup and backups (data-model.md, Cleanup)."""

import calendar
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from reminder_bot.clock import Clock
from reminder_bot.storage.db import Database
from reminder_bot.storage.repositories import Repository

logger = logging.getLogger(__name__)

BLOCKED_MONTHS = 12
DELIVERY_RETENTION = timedelta(days=90)
BACKUP_DAYS_KEPT = 7
_BACKUP_NAME = re.compile(r"reminders-(\d{8})\.db")


def months_before(moment: datetime, months: int) -> datetime:
    """The same day `months` earlier, or that month's last day if it's shorter."""
    year, month_index = divmod(moment.year * 12 + moment.month - 1 - months, 12)
    month = month_index + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


class Maintenance:
    def __init__(self, db: Database, repo: Repository, clock: Clock, backup_dir: Path) -> None:
        self._db = db
        self._repo = repo
        self._clock = clock
        self._backup_dir = backup_dir
        self._last_run: datetime | None = None

    async def run_if_due(self) -> bool:
        now = self._clock.now()
        if self._last_run is not None and now - self._last_run < timedelta(days=1):
            return False
        await self.run()
        return True

    async def run(self) -> None:
        now = self._clock.now()
        self._last_run = now
        users = await self._repo.delete_users_blocked_before(months_before(now, BLOCKED_MONTHS))
        records = await self._repo.delete_deliveries_before(now - DELIVERY_RETENTION)
        logger.info("maintenance_cleanup users_deleted=%s deliveries_deleted=%s", users, records)
        # Cleanup runs first, so deleted data leaves backups within a week.
        await self._back_up(now.date())
        self._prune_backups(now.date())

    async def _back_up(self, today: date) -> None:
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        target = self._backup_dir / f"reminders-{today:%Y%m%d}.db"
        partial = target.with_suffix(".db.tmp")
        partial.unlink(missing_ok=True)
        await self._db.backup_to(partial)
        os.replace(partial, target)
        logger.info("backup_written name=%s", target.name)

    def _prune_backups(self, today: date) -> None:
        oldest_kept = today - timedelta(days=BACKUP_DAYS_KEPT - 1)
        for path in self._backup_dir.iterdir():
            match = _BACKUP_NAME.fullmatch(path.name)
            if match and datetime.strptime(match.group(1), "%Y%m%d").date() < oldest_kept:
                path.unlink()
