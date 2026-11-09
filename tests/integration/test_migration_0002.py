"""Migration 0002 turns users into chats without changing existing data (data-model.md)."""

from pathlib import Path

from reminder_bot.storage.db import Database

NOW = "2026-11-06T12:00:00Z"
BLOCKED = "2026-10-01T09:00:00Z"


async def old_database(tmp_path: Path) -> Database:
    db = await Database.open(tmp_path / "old.db")
    await db.migrate(up_to=1)
    await db.execute(
        "INSERT INTO users (id, language, blocked_at, created_at) VALUES (7, 'uk', ?, ?)",
        (BLOCKED, NOW),
    )
    for message_id, status, next_send in ((1, "active", NOW), (2, "completed", None)):
        await db.execute(
            "INSERT INTO scheduled_messages (id, user_id, text, recurrence, start_date,"
            " send_time, next_send_at, status, created_at, updated_at)"
            " VALUES (?, 7, 'Pay rent', 'once', '2026-11-07', '14:45', ?, ?, ?, ?)",
            (message_id, next_send, status, NOW, NOW),
        )
    await db.execute(
        "INSERT INTO deliveries (message_id, scheduled_at, status, created_at)"
        " VALUES (2, '2026-11-07T12:45:00Z', 'sent', ?)",
        (NOW,),
    )
    return db


async def test_existing_rows_keep_their_ids_and_meaning(tmp_path: Path) -> None:
    db = await old_database(tmp_path)
    await db.migrate()
    assert (await db.fetch_one("PRAGMA user_version"))[0] >= 2

    chat = await db.fetch_one("SELECT * FROM chats WHERE id = 7")
    assert chat["kind"] == "private"
    assert chat["language"] == "uk"
    assert chat["unreachable_at"] == BLOCKED

    rows = await db.fetch_all("SELECT * FROM scheduled_messages ORDER BY id")
    assert [(row["id"], row["chat_id"], row["status"]) for row in rows] == [
        (1, 7, "active"),
        (2, 7, "completed"),
    ]
    assert all(row["created_by_name"] is None and row["changed_by_name"] is None for row in rows)
    assert (await db.fetch_one("SELECT COUNT(*) FROM deliveries"))[0] == 1
    await db.close()


async def test_deleting_a_chat_still_cascades(tmp_path: Path) -> None:
    db = await old_database(tmp_path)
    await db.migrate()
    await db.execute("DELETE FROM chats WHERE id = 7")
    assert (await db.fetch_one("SELECT COUNT(*) FROM scheduled_messages"))[0] == 0
    assert (await db.fetch_one("SELECT COUNT(*) FROM deliveries"))[0] == 0
    await db.close()


async def test_chat_index_replaces_the_user_index(tmp_path: Path) -> None:
    db = await old_database(tmp_path)
    await db.migrate()
    names = {
        row["name"]
        for row in await db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert "idx_messages_chat" in names
    assert "idx_messages_user" not in names
    await db.close()


async def test_kind_only_allows_private_or_group(tmp_path: Path) -> None:
    db = await old_database(tmp_path)
    await db.migrate()
    await db.execute(
        "INSERT INTO chats (id, kind, language, created_at) VALUES (-100, 'group', 'en', ?)", (NOW,)
    )
    try:
        await db.execute(
            "INSERT INTO chats (id, kind, language, created_at) VALUES (-200, 'channel', 'en', ?)",
            (NOW,),
        )
    except Exception as error:
        assert "CHECK" in str(error)
    else:
        raise AssertionError("A channel chat was accepted")
    await db.close()
