"""All SQL. Every user-facing query is scoped to the chat that asked (001 FR-021, 002 FR-107).

A chat is a private chat, whose ID is the person's Telegram ID, or a group.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from reminder_bot.domain.schedule import Recurrence, Rule, first_send, next_after
from reminder_bot.storage.db import Database, Transaction

MAX_ACTIVE_MESSAGES = 100
_MAX_RETRY_DELAY_SECONDS = 300
_FIRST_RETRY_DELAY_SECONDS = 30


class LimitReached(Exception):
    """The chat already has the maximum number of active messages."""


class DateTimeInPast(Exception):
    """The requested schedule has no send in the future."""


def to_db(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_db(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


@dataclass(frozen=True)
class Chat:
    id: int
    language: str
    unreachable_at: datetime | None
    kind: str = "private"

    @property
    def is_group(self) -> bool:
        return self.kind == "group"


@dataclass(frozen=True)
class Message:
    id: int
    chat_id: int
    text: str
    recurrence: Recurrence
    start_date: date
    send_time: time
    interval_days: int | None
    next_send_at: datetime | None
    status: str
    not_delivered: bool = False
    created_by_name: str | None = None
    changed_by_name: str | None = None

    @property
    def rule(self) -> Rule:
        return Rule(self.recurrence, self.start_date, self.send_time, self.interval_days)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class Claim:
    """A send the dispatcher now owns and must report an outcome for."""

    delivery_id: int
    message_id: int
    chat_id: int
    language: str
    text: str
    scheduled_at: datetime


@dataclass(frozen=True)
class DueMessage:
    message_id: int
    chat_id: int


@dataclass(frozen=True)
class DueRetry:
    delivery_id: int
    message_id: int
    chat_id: int


def _chat(row) -> Chat:
    return Chat(
        id=row["id"],
        language=row["language"],
        unreachable_at=from_db(row["unreachable_at"]) if row["unreachable_at"] else None,
        kind=row["kind"],
    )


def _message(row, *, not_delivered: bool = False) -> Message:
    return Message(
        id=row["id"],
        chat_id=row["chat_id"],
        text=row["text"],
        recurrence=Recurrence(row["recurrence"]),
        start_date=date.fromisoformat(row["start_date"]),
        send_time=time.fromisoformat(row["send_time"]),
        interval_days=row["interval_days"],
        next_send_at=from_db(row["next_send_at"]) if row["next_send_at"] else None,
        status=row["status"],
        not_delivered=not_delivered,
        created_by_name=row["created_by_name"],
        changed_by_name=row["changed_by_name"],
    )


# A completed message "shows as not delivered" when its latest real attempt failed.
_LAST_DELIVERY = (
    "(SELECT d.status FROM deliveries d WHERE d.message_id = m.id AND d.status != 'blocked'"
    " ORDER BY d.id DESC LIMIT 1) AS last_delivery"
)


def _listed_message(row) -> Message:
    not_delivered = row["status"] == "completed" and row["last_delivery"] == "failed"
    return _message(row, not_delivered=not_delivered)


class Repository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # Chats

    async def get_or_create_chat(
        self,
        chat_id: int,
        telegram_language: str | None,
        now: datetime,
        kind: str = "private",
    ) -> Chat:
        """Load a chat, creating it with a language from the Telegram setting if it's new."""
        language = "uk" if (telegram_language or "").lower().split("-")[0] == "uk" else "en"
        async with self._db.transaction() as tx:
            await tx.execute(
                "INSERT INTO chats (id, kind, language, created_at) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (id) DO NOTHING",
                (chat_id, kind, language, to_db(now)),
            )
            return _chat(await tx.fetch_one("SELECT * FROM chats WHERE id = ?", (chat_id,)))

    async def get_chat(self, chat_id: int) -> Chat | None:
        row = await self._db.fetch_one("SELECT * FROM chats WHERE id = ?", (chat_id,))
        return _chat(row) if row else None

    async def set_language(self, chat_id: int, language: str) -> None:
        await self._db.execute("UPDATE chats SET language = ? WHERE id = ?", (language, chat_id))

    async def set_unreachable(self, chat_id: int, now: datetime) -> None:
        await self._db.execute(
            "UPDATE chats SET unreachable_at = ? WHERE id = ? AND unreachable_at IS NULL",
            (to_db(now), chat_id),
        )

    async def set_reachable(self, chat_id: int, now: datetime) -> None:
        """Clear a block or an unreachable group. Recurring messages move ahead with no
        catch-up (001 FR-013a, 002 FR-115).

        One-time messages keep their time, so an overdue one still goes out once.
        """
        async with self._db.transaction() as tx:
            row = await tx.fetch_one("SELECT unreachable_at FROM chats WHERE id = ?", (chat_id,))
            if row is None or row["unreachable_at"] is None:
                return
            await tx.execute("UPDATE chats SET unreachable_at = NULL WHERE id = ?", (chat_id,))
            rows = await tx.fetch_all(
                "SELECT * FROM scheduled_messages WHERE chat_id = ? AND status = 'active'"
                " AND recurrence != 'once' AND next_send_at <= ?",
                (chat_id, to_db(now)),
            )
            for overdue in rows:
                message = _message(overdue)
                await tx.execute(
                    "UPDATE scheduled_messages SET next_send_at = ? WHERE id = ?",
                    (to_db(next_after(message.rule, now)), message.id),
                )
            # A retry of a recurring send from before the block would be a catch-up.
            await tx.execute(
                "UPDATE deliveries SET status = 'blocked', next_attempt_at = NULL"
                " WHERE status = 'retrying' AND message_id IN (SELECT id FROM scheduled_messages"
                " WHERE chat_id = ? AND recurrence != 'once')",
                (chat_id,),
            )

    # Messages

    async def count_active(self, chat_id: int) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) FROM scheduled_messages WHERE chat_id = ? AND status = 'active'",
            (chat_id,),
        )
        return row[0]

    async def create_message(
        self,
        chat_id: int,
        text: str,
        rule: Rule,
        now: datetime,
        created_by_name: str | None = None,
    ) -> Message:
        async with self._db.transaction() as tx:
            count = await tx.fetch_one(
                "SELECT COUNT(*) FROM scheduled_messages WHERE chat_id = ? AND status = 'active'",
                (chat_id,),
            )
            if count[0] >= MAX_ACTIVE_MESSAGES:
                raise LimitReached
            cursor = await tx.execute(
                "INSERT INTO scheduled_messages (chat_id, text, recurrence, start_date, send_time,"
                " interval_days, next_send_at, status, created_by_name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                (
                    chat_id,
                    text,
                    rule.recurrence.value,
                    rule.start_date.isoformat(),
                    rule.send_time.strftime("%H:%M"),
                    rule.interval_days,
                    to_db(first_send(rule)),
                    created_by_name,
                    to_db(now),
                    to_db(now),
                ),
            )
            row = await tx.fetch_one(
                "SELECT * FROM scheduled_messages WHERE id = ?", (cursor.lastrowid,)
            )
            return _message(row)

    async def get_message(self, chat_id: int, message_id: int) -> Message | None:
        row = await self._db.fetch_one(
            f"SELECT m.*, {_LAST_DELIVERY} FROM scheduled_messages m"
            " WHERE m.id = ? AND m.chat_id = ?",
            (message_id, chat_id),
        )
        return _listed_message(row) if row else None

    async def list_messages(
        self, chat_id: int, page: int, page_size: int
    ) -> tuple[list[Message], int]:
        """Active messages first by next send date, then completed ones (FR-015)."""
        total = await self._db.fetch_one(
            "SELECT COUNT(*) FROM scheduled_messages WHERE chat_id = ?", (chat_id,)
        )
        rows = await self._db.fetch_all(
            f"SELECT m.*, {_LAST_DELIVERY} FROM scheduled_messages m WHERE m.chat_id = ?"
            " ORDER BY m.status = 'completed', m.next_send_at IS NOT NULL, m.next_send_at, m.id"
            " LIMIT ? OFFSET ?",
            (chat_id, page_size, page * page_size),
        )
        return [_listed_message(row) for row in rows], total[0]

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        async with self._db.transaction() as tx:
            cursor = await tx.execute(
                "DELETE FROM scheduled_messages WHERE id = ? AND chat_id = ?",
                (message_id, chat_id),
            )
            return cursor.rowcount > 0

    async def update_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        now: datetime,
        changed_by_name: str | None = None,
    ) -> Message | None:
        """Change only the text. The schedule stays as it is."""
        async with self._db.transaction() as tx:
            await tx.execute(
                "UPDATE scheduled_messages SET text = ?, updated_at = ?,"
                " changed_by_name = COALESCE(?, changed_by_name)"
                " WHERE id = ? AND chat_id = ? AND status = 'active'",
                (text, to_db(now), changed_by_name, message_id, chat_id),
            )
            row = await tx.fetch_one(
                "SELECT * FROM scheduled_messages"
                " WHERE id = ? AND chat_id = ? AND status = 'active'",
                (message_id, chat_id),
            )
            return _message(row) if row else None

    async def update_schedule(
        self,
        chat_id: int,
        message_id: int,
        rule: Rule,
        now: datetime,
        changed_by_name: str | None = None,
    ) -> Message | None:
        """Replace a message's schedule. No send based on the old values can follow.

        Returns None if the message is gone or completed. Raises DateTimeInPast if
        the new schedule has no send ahead.
        """
        next_send = next_after(rule, now)
        if next_send is None:
            raise DateTimeInPast
        async with self._db.transaction() as tx:
            cursor = await tx.execute(
                "UPDATE scheduled_messages SET recurrence = ?, start_date = ?, send_time = ?,"
                " interval_days = ?, next_send_at = ?, updated_at = ?,"
                " changed_by_name = COALESCE(?, changed_by_name)"
                " WHERE id = ? AND chat_id = ? AND status = 'active'",
                (
                    rule.recurrence.value,
                    rule.start_date.isoformat(),
                    rule.send_time.strftime("%H:%M"),
                    rule.interval_days,
                    to_db(next_send),
                    to_db(now),
                    changed_by_name,
                    message_id,
                    chat_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await tx.execute(
                "UPDATE deliveries SET status = 'failed', error = 'superseded',"
                " next_attempt_at = NULL WHERE message_id = ? AND status = 'retrying'",
                (message_id,),
            )
            row = await tx.fetch_one("SELECT * FROM scheduled_messages WHERE id = ?", (message_id,))
            return _message(row)

    # Delivery

    async def due_messages(self, now: datetime, limit: int) -> list[DueMessage]:
        rows = await self._db.fetch_all(
            "SELECT m.id, m.chat_id FROM scheduled_messages m JOIN chats u ON u.id = m.chat_id"
            " WHERE m.status = 'active' AND m.next_send_at <= ? AND u.unreachable_at IS NULL"
            " ORDER BY m.next_send_at, m.id LIMIT ?",
            (to_db(now), limit),
        )
        return [DueMessage(row["id"], row["chat_id"]) for row in rows]

    async def claim(self, message_id: int, now: datetime) -> Claim | None:
        """Record a send and advance the schedule. Send only after this returns a claim."""
        async with self._db.transaction() as tx:
            row = await tx.fetch_one(
                "SELECT m.*, u.language, u.unreachable_at FROM scheduled_messages m"
                " JOIN chats u ON u.id = m.chat_id WHERE m.id = ?",
                (message_id,),
            )
            if (
                row is None
                or row["status"] != "active"
                or row["unreachable_at"] is not None
                or row["next_send_at"] is None
                or row["next_send_at"] > to_db(now)
            ):
                return None
            message = _message(row)
            once = message.recurrence is Recurrence.ONCE
            next_send = None if once else next_after(message.rule, now)
            await tx.execute(
                "UPDATE scheduled_messages SET next_send_at = ? WHERE id = ?",
                (to_db(next_send) if next_send else None, message_id),
            )
            if not once:
                # An earlier send still retrying will deliver this message once.
                retrying = await tx.fetch_one(
                    "SELECT 1 FROM deliveries WHERE message_id = ? AND status = 'retrying'",
                    (message_id,),
                )
                if retrying:
                    return None
            try:
                cursor = await tx.execute(
                    "INSERT INTO deliveries"
                    " (message_id, scheduled_at, status, attempts, created_at)"
                    " VALUES (?, ?, 'sending', 1, ?)",
                    (message_id, row["next_send_at"], to_db(now)),
                )
            except sqlite3.IntegrityError:
                # This send already happened, so it must not happen twice (FR-010).
                if once:
                    await self._complete_once(tx, message_id, now)
                return None
            return Claim(
                delivery_id=cursor.lastrowid,
                message_id=message_id,
                chat_id=message.chat_id,
                language=row["language"],
                text=message.text,
                scheduled_at=message.next_send_at,
            )

    async def due_retries(self, now: datetime, limit: int) -> list[DueRetry]:
        rows = await self._db.fetch_all(
            "SELECT d.id, d.message_id, m.chat_id FROM deliveries d"
            " JOIN scheduled_messages m ON m.id = d.message_id"
            " JOIN chats u ON u.id = m.chat_id"
            " WHERE d.status = 'retrying' AND d.next_attempt_at <= ? AND u.unreachable_at IS NULL"
            " ORDER BY d.next_attempt_at, d.id LIMIT ?",
            (to_db(now), limit),
        )
        return [DueRetry(row["id"], row["message_id"], row["chat_id"]) for row in rows]

    async def claim_retry(self, delivery_id: int, now: datetime) -> Claim | None:
        """Take a retry for sending. It uses the message's current text."""
        async with self._db.transaction() as tx:
            row = await tx.fetch_one(
                "SELECT d.scheduled_at, d.message_id, m.chat_id, m.text, u.language"
                " FROM deliveries d JOIN scheduled_messages m ON m.id = d.message_id"
                " JOIN chats u ON u.id = m.chat_id"
                " WHERE d.id = ? AND d.status = 'retrying' AND d.next_attempt_at <= ?"
                " AND u.unreachable_at IS NULL",
                (delivery_id, to_db(now)),
            )
            if row is None:
                return None
            await tx.execute(
                "UPDATE deliveries SET status = 'sending', next_attempt_at = NULL,"
                " attempts = attempts + 1 WHERE id = ?",
                (delivery_id,),
            )
            return Claim(
                delivery_id=delivery_id,
                message_id=row["message_id"],
                chat_id=row["chat_id"],
                language=row["language"],
                text=row["text"],
                scheduled_at=from_db(row["scheduled_at"]),
            )

    async def _complete_once(self, tx: Transaction, message_id: int, now: datetime) -> None:
        # A rescheduled message has a next send again, and stays active.
        await tx.execute(
            "UPDATE scheduled_messages SET status = 'completed', updated_at = ?"
            " WHERE id = ? AND recurrence = 'once' AND status = 'active'"
            " AND next_send_at IS NULL",
            (to_db(now), message_id),
        )

    async def _finish(
        self, delivery_id: int, status: str, now: datetime, error: str | None = None
    ) -> None:
        async with self._db.transaction() as tx:
            await self._finish_in(tx, delivery_id, status, now, error)

    async def _finish_in(
        self, tx: Transaction, delivery_id: int, status: str, now: datetime, error: str | None
    ) -> None:
        await tx.execute(
            "UPDATE deliveries SET status = ?, error = ?, next_attempt_at = NULL,"
            " sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END WHERE id = ?",
            (status, error, status, to_db(now), delivery_id),
        )
        row = await tx.fetch_one("SELECT message_id FROM deliveries WHERE id = ?", (delivery_id,))
        if row:
            await self._complete_once(tx, row["message_id"], now)

    async def record_sent(self, delivery_id: int, now: datetime) -> None:
        await self._finish(delivery_id, "sent", now)

    async def record_failed(self, delivery_id: int, now: datetime, error: str) -> None:
        await self._finish(delivery_id, "failed", now, error)

    async def record_unknown(self, delivery_id: int, now: datetime, error: str) -> None:
        await self._finish(delivery_id, "unknown", now, error)

    async def record_retry(
        self, delivery_id: int, now: datetime, error: str, retry_after: int | None = None
    ) -> None:
        """Save a send to try again, so it survives restarts."""
        async with self._db.transaction() as tx:
            row = await tx.fetch_one("SELECT attempts FROM deliveries WHERE id = ?", (delivery_id,))
            if row is None:
                return
            if retry_after is None:
                # Doubles from 30 seconds. The cap keeps the exponent from growing unbounded.
                exponent = min(row["attempts"] - 1, 10)
                delay = min(_FIRST_RETRY_DELAY_SECONDS * 2**exponent, _MAX_RETRY_DELAY_SECONDS)
            else:
                delay = retry_after
            await tx.execute(
                "UPDATE deliveries SET status = 'retrying', error = ?, next_attempt_at = ?"
                " WHERE id = ?",
                (error, to_db(now + timedelta(seconds=delay)), delivery_id),
            )

    async def record_blocked(self, claim: Claim, now: datetime) -> None:
        """Telegram says the chat can't be reached: a person blocked the bot, or the bot
        can't post in a group. A one-time message keeps its time."""
        async with self._db.transaction() as tx:
            await tx.execute(
                "UPDATE deliveries SET status = 'blocked', next_attempt_at = NULL WHERE id = ?",
                (claim.delivery_id,),
            )
            await tx.execute(
                "UPDATE scheduled_messages SET next_send_at = ?"
                " WHERE id = ? AND recurrence = 'once' AND status = 'active'"
                " AND next_send_at IS NULL",
                (to_db(claim.scheduled_at), claim.message_id),
            )
            await tx.execute(
                "UPDATE chats SET unreachable_at = ? WHERE id = ? AND unreachable_at IS NULL",
                (to_db(now), claim.chat_id),
            )

    async def mark_leftover_sends_unknown(self, now: datetime) -> int:
        """After a restart, a send still marked `sending` may or may not have arrived."""
        async with self._db.transaction() as tx:
            rows = await tx.fetch_all("SELECT id FROM deliveries WHERE status = 'sending'")
            for row in rows:
                await self._finish_in(tx, row["id"], "unknown", now, "interrupted")
            return len(rows)

    # Maintenance

    async def move_chat(self, old_id: int, new_id: int) -> bool:
        """Move a group to the ID Telegram gave it when upgrading it (002 FR-116).

        Deliveries follow their reminders, so nothing is sent twice. A repeat call for a
        move that already happened does nothing.
        """
        async with self._db.transaction() as tx:
            old = await tx.fetch_one("SELECT * FROM chats WHERE id = ?", (old_id,))
            if old is None:
                return False
            await tx.execute(
                "INSERT INTO chats (id, kind, language, unreachable_at, created_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
                (new_id, old["kind"], old["language"], old["unreachable_at"], old["created_at"]),
            )
            await tx.execute(
                "UPDATE scheduled_messages SET chat_id = ? WHERE chat_id = ?", (new_id, old_id)
            )
            await tx.execute("DELETE FROM chats WHERE id = ?", (old_id,))
            return True

    async def delete_chats_unreachable_before(self, cutoff: datetime) -> int:
        async with self._db.transaction() as tx:
            cursor = await tx.execute(
                "DELETE FROM chats WHERE unreachable_at IS NOT NULL AND unreachable_at <= ?",
                (to_db(cutoff),),
            )
            return cursor.rowcount

    async def delete_deliveries_before(self, cutoff: datetime) -> int:
        async with self._db.transaction() as tx:
            cursor = await tx.execute(
                "DELETE FROM deliveries WHERE created_at < ?"
                " AND status NOT IN ('sending', 'retrying')",
                (to_db(cutoff),),
            )
            return cursor.rowcount
