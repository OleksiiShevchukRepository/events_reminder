"""SQLite connection and migrations.

Handlers and the scheduler share one connection, so a lock keeps one coroutine's
transaction from interleaving with another's statements.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path
from typing import Any

import aiosqlite

# At DEBUG level aiosqlite logs every statement with its values, including reminder
# text. Reminder text must never reach the logs, whatever LOG_LEVEL is set to.
logging.getLogger("aiosqlite").setLevel(logging.WARNING)


class Transaction:
    """Statements run inside a transaction that already holds the lock."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def execute(self, sql: str, parameters: Iterable[Any] = ()) -> aiosqlite.Cursor:
        return await self._connection.execute(sql, tuple(parameters))

    async def fetch_one(self, sql: str, parameters: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self._connection.execute(sql, tuple(parameters)) as cursor:
            return await cursor.fetchone()

    async def fetch_all(self, sql: str, parameters: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self._connection.execute(sql, tuple(parameters)) as cursor:
            return list(await cursor.fetchall())


class Database:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path) -> Database:
        # isolation_level=None leaves transaction control to `transaction()` below.
        connection = await aiosqlite.connect(path, isolation_level=None)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA busy_timeout = 5000")
        return cls(connection)

    async def close(self) -> None:
        await self._connection.close()

    async def migrate(self) -> None:
        directory = resources.files("reminder_bot.storage") / "migrations"
        scripts = sorted(
            (item for item in directory.iterdir() if item.name.endswith(".sql")),
            key=lambda item: item.name,
        )
        async with self._lock:
            async with self._connection.execute("PRAGMA user_version") as cursor:
                version = (await cursor.fetchone())[0]
            for script in scripts:
                number = int(script.name.split("_", 1)[0])
                if number <= version:
                    continue
                body = script.read_text(encoding="utf-8")
                # The version is set in the same transaction as the changes it records.
                await self._connection.executescript(
                    f"BEGIN IMMEDIATE;\n{body}\nPRAGMA user_version = {number};\nCOMMIT;"
                )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        async with self._lock:
            await self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield Transaction(self._connection)
            except BaseException:
                await self._connection.execute("ROLLBACK")
                raise
            else:
                await self._connection.execute("COMMIT")

    async def execute(self, sql: str, parameters: Iterable[Any] = ()) -> None:
        async with self._lock:
            await self._connection.execute(sql, tuple(parameters))

    async def fetch_one(self, sql: str, parameters: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self._lock:
            async with self._connection.execute(sql, tuple(parameters)) as cursor:
                return await cursor.fetchone()

    async def fetch_all(self, sql: str, parameters: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            async with self._connection.execute(sql, tuple(parameters)) as cursor:
                return list(await cursor.fetchall())

    async def backup_to(self, path: Path) -> None:
        """Write a consistent copy of the database to `path`."""
        async with self._lock:
            await self._connection.execute("VACUUM INTO ?", (str(path),))
