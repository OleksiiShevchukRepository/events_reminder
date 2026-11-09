from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from reminder_bot.clock import FixedClock
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.scheduler.maintenance import Maintenance, months_before
from reminder_bot.storage.db import Database
from reminder_bot.storage.repositories import Repository

USER = 1001
BLOCKED_AT = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
RULE = Rule(Recurrence.DAILY, date(2026, 3, 16), time(9, 0))


@pytest.fixture
def maintenance(db: Database, repo: Repository, clock: FixedClock, tmp_path: Path) -> Maintenance:
    return Maintenance(db, repo, clock, tmp_path / "backups")


async def blocked_user(repo: Repository) -> int:
    await repo.get_or_create_chat(USER, "en", BLOCKED_AT)
    message = await repo.create_message(USER, "x", RULE, BLOCKED_AT)
    await repo.set_unreachable(USER, BLOCKED_AT)
    return message.id


def test_months_before_clamps_to_the_last_day_of_the_month() -> None:
    assert months_before(datetime(2028, 2, 29, tzinfo=UTC), 12) == datetime(2027, 2, 28, tzinfo=UTC)
    assert months_before(datetime(2027, 3, 15, tzinfo=UTC), 12) == datetime(2026, 3, 15, tzinfo=UTC)


async def test_user_is_kept_until_12_calendar_months_blocked(
    repo: Repository, clock: FixedClock, maintenance: Maintenance
) -> None:
    await blocked_user(repo)
    clock.set(datetime(2027, 3, 15, 9, 59, tzinfo=UTC))
    await maintenance.run()
    assert await repo.get_chat(USER) is not None


async def test_user_and_their_data_are_deleted_after_12_calendar_months(
    db: Database, repo: Repository, clock: FixedClock, maintenance: Maintenance
) -> None:
    message_id = await blocked_user(repo)
    await db.execute(
        "INSERT INTO deliveries (message_id, scheduled_at, status, created_at)"
        " VALUES (?, '2026-03-16T07:00:00Z', 'sent', '2027-03-15T10:00:00Z')",
        (message_id,),
    )
    clock.set(datetime(2027, 3, 15, 10, 0, tzinfo=UTC))
    await maintenance.run()
    assert await repo.get_chat(USER) is None
    assert (await db.fetch_one("SELECT COUNT(*) FROM scheduled_messages"))[0] == 0
    assert (await db.fetch_one("SELECT COUNT(*) FROM deliveries"))[0] == 0


async def test_unblocking_resets_the_period(
    repo: Repository, clock: FixedClock, maintenance: Maintenance
) -> None:
    await blocked_user(repo)
    await repo.set_reachable(USER, datetime(2026, 9, 1, tzinfo=UTC))
    await repo.set_unreachable(USER, datetime(2027, 1, 1, tzinfo=UTC))
    clock.set(datetime(2027, 3, 16, tzinfo=UTC))
    await maintenance.run()
    assert await repo.get_chat(USER) is not None


async def test_users_who_never_blocked_the_bot_are_kept(
    repo: Repository, clock: FixedClock, maintenance: Maintenance
) -> None:
    await repo.get_or_create_chat(USER, "en", BLOCKED_AT)
    clock.set(BLOCKED_AT + timedelta(days=5000))
    await maintenance.run()
    assert await repo.get_chat(USER) is not None


async def insert_delivery(db: Database, message_id: int, day: int, status: str, created: str):
    await db.execute(
        "INSERT INTO deliveries (message_id, scheduled_at, status, created_at) VALUES (?, ?, ?, ?)",
        (message_id, f"2026-01-{day:02d}T07:00:00Z", status, created),
    )


async def test_delivery_records_are_deleted_after_90_days(
    db: Database, repo: Repository, clock: FixedClock, maintenance: Maintenance
) -> None:
    await repo.get_or_create_chat(USER, "en", clock.now())
    message = await repo.create_message(USER, "x", RULE, clock.now())
    now = clock.now()
    old = (now - timedelta(days=90, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    kept = (now - timedelta(days=89)).strftime("%Y-%m-%dT%H:%M:%SZ")
    await insert_delivery(db, message.id, 1, "sent", old)
    await insert_delivery(db, message.id, 2, "sent", kept)
    await insert_delivery(db, message.id, 3, "retrying", old)
    await maintenance.run()
    rows = await db.fetch_all("SELECT status, created_at FROM deliveries ORDER BY id")
    assert [(r["status"], r["created_at"]) for r in rows] == [("sent", kept), ("retrying", old)]


async def test_backup_is_a_usable_copy(
    repo: Repository, clock: FixedClock, maintenance: Maintenance, tmp_path: Path
) -> None:
    await repo.get_or_create_chat(USER, "en", clock.now())
    await maintenance.run()
    files = list((tmp_path / "backups").glob("*.db"))
    assert len(files) == 1
    copy = await Database.open(files[0])
    assert (await copy.fetch_one("SELECT COUNT(*) FROM chats"))[0] == 1
    await copy.close()


async def test_running_twice_on_a_day_keeps_one_backup(
    clock: FixedClock, maintenance: Maintenance, tmp_path: Path
) -> None:
    await maintenance.run()
    clock.advance(hours=1)
    await maintenance.run()
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


async def test_only_seven_days_of_backups_are_kept(
    clock: FixedClock, maintenance: Maintenance, tmp_path: Path
) -> None:
    for _ in range(10):
        await maintenance.run()
        clock.advance(days=1)
    names = sorted(path.name for path in (tmp_path / "backups").glob("*.db"))
    assert len(names) == 7
    # The last run is on 15 November, which keeps 9-15 November.
    assert names[0] == "reminders-20261109.db"


async def test_unrelated_files_in_the_backup_folder_are_left_alone(
    clock: FixedClock, maintenance: Maintenance, tmp_path: Path
) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "notes.txt").write_text("keep me")
    clock.advance(days=30)
    await maintenance.run()
    assert (backups / "notes.txt").exists()


async def test_due_check_runs_once_a_day(
    clock: FixedClock, maintenance: Maintenance, tmp_path: Path
) -> None:
    assert await maintenance.run_if_due() is True
    clock.advance(hours=23)
    assert await maintenance.run_if_due() is False
    clock.advance(hours=1)
    assert await maintenance.run_if_due() is True
