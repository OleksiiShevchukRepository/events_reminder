import sqlite3
from pathlib import Path

import pytest

from reminder_bot.storage.db import Database

NOW = "2026-11-06T12:00:00Z"


async def open_db(tmp_path: Path) -> Database:
    db = await Database.open(tmp_path / "test.db")
    await db.migrate()
    return db


async def insert_message(db: Database) -> int:
    await db.execute("INSERT INTO chats (id, language, created_at) VALUES (1, 'en', ?)", (NOW,))
    await db.execute(
        "INSERT INTO scheduled_messages (id, chat_id, text, recurrence, start_date, send_time,"
        " status, created_at, updated_at)"
        " VALUES (1, 1, 'x', 'once', '2026-11-07', '14:45', 'active', ?, ?)",
        (NOW, NOW),
    )
    return 1


async def insert_delivery(db: Database, status: str) -> None:
    await db.execute(
        "INSERT INTO deliveries (message_id, scheduled_at, status, created_at)"
        " VALUES (1, '2026-11-07T12:45:00Z', ?, ?)",
        (status, NOW),
    )


async def test_migrations_apply_once_and_are_tracked(tmp_path: Path) -> None:
    db = await open_db(tmp_path)
    assert (await db.fetch_one("PRAGMA user_version"))[0] == 2
    await db.migrate()  # A second run must not fail or re-apply anything.
    assert (await db.fetch_one("PRAGMA user_version"))[0] == 2
    await db.close()

    reopened = await Database.open(tmp_path / "test.db")
    await reopened.migrate()
    assert (await reopened.fetch_one("PRAGMA user_version"))[0] == 2
    await reopened.close()


async def test_wal_mode_and_foreign_keys_are_on(tmp_path: Path) -> None:
    db = await open_db(tmp_path)
    assert (await db.fetch_one("PRAGMA journal_mode"))[0] == "wal"
    assert (await db.fetch_one("PRAGMA foreign_keys"))[0] == 1
    await db.close()


async def test_deleting_a_user_cascades(tmp_path: Path) -> None:
    db = await open_db(tmp_path)
    await insert_message(db)
    await insert_delivery(db, "sent")
    await db.execute("DELETE FROM chats WHERE id = 1")
    assert (await db.fetch_one("SELECT COUNT(*) FROM scheduled_messages"))[0] == 0
    assert (await db.fetch_one("SELECT COUNT(*) FROM deliveries"))[0] == 0
    await db.close()


async def test_second_delivery_for_the_same_send_is_rejected(tmp_path: Path) -> None:
    db = await open_db(tmp_path)
    await insert_message(db)
    await insert_delivery(db, "sending")
    with pytest.raises(sqlite3.IntegrityError):
        await insert_delivery(db, "sending")
    await db.close()


async def test_blocked_delivery_does_not_prevent_a_new_claim(tmp_path: Path) -> None:
    db = await open_db(tmp_path)
    await insert_message(db)
    await insert_delivery(db, "blocked")
    await insert_delivery(db, "sending")
    assert (await db.fetch_one("SELECT COUNT(*) FROM deliveries"))[0] == 2
    await db.close()


async def test_failed_transaction_rolls_back(tmp_path: Path) -> None:
    db = await open_db(tmp_path)
    with pytest.raises(RuntimeError):
        async with db.transaction() as tx:
            await tx.execute(
                "INSERT INTO chats (id, language, created_at) VALUES (1, 'en', ?)", (NOW,)
            )
            raise RuntimeError("boom")
    assert (await db.fetch_one("SELECT COUNT(*) FROM chats"))[0] == 0
    await db.close()
