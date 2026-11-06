"""Sends messages that are due.

Each send is claimed in the database just before it's sent, which is what prevents
duplicates (FR-010). See the Delivery section of research.md for the failure rules.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import (
    RestartingTelegram,
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from reminder_bot.bot.session import TelegramGatewayError
from reminder_bot.bot.views import format_when
from reminder_bot.clock import Clock
from reminder_bot.i18n import translate
from reminder_bot.storage.repositories import Claim, Repository

logger = logging.getLogger(__name__)

POLL_SECONDS = 5
BATCH_SIZE = 2000
SHUTDOWN_GRACE_SECONDS = 25
OVERDUE_NOTE_AFTER = timedelta(minutes=1)
OVERALL_SPACING = timedelta(seconds=1 / 25)
PER_CHAT_SPACING = timedelta(seconds=1)
_MAX_TRACKED_CHATS = 10_000


def _connection_never_made(error: TelegramNetworkError) -> bool:
    # aiogram puts the aiohttp error's class name first in the message. Any other
    # network error, such as a timeout or a dropped connection, may have reached Telegram.
    return str(error.message).startswith(("ClientConnector", "ClientProxyConnection"))


class RateLimiter:
    """Keeps sending under Telegram's limits by reserving each send a future time slot."""

    def __init__(
        self, clock: Clock, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._overall_next: datetime | None = None
        self._chat_next: dict[int, datetime] = {}

    async def acquire(self, chat_id: int) -> None:
        now = self._clock.now()
        slot = max(
            now,
            self._overall_next or now,
            self._chat_next.get(chat_id, now),
        )
        self._overall_next = slot + OVERALL_SPACING
        if len(self._chat_next) > _MAX_TRACKED_CHATS:
            self._chat_next = {k: v for k, v in self._chat_next.items() if v > now}
        self._chat_next[chat_id] = slot + PER_CHAT_SPACING
        wait = (slot - now).total_seconds()
        if wait > 0:
            await self._sleep(wait)

    def pause(self, seconds: float) -> None:
        """Telegram asked for a pause, which applies to all sending."""
        until = self._clock.now() + timedelta(seconds=seconds)
        self._overall_next = max(self._overall_next or until, until)


class MessageDispatcher:
    def __init__(
        self,
        repo: Repository,
        bot: Bot,
        clock: Clock,
        limiter: RateLimiter,
        heartbeat_path: Path,
    ) -> None:
        self.repo = repo
        self.bot = bot
        self.clock = clock
        self.limiter = limiter
        self.heartbeat_path = heartbeat_path
        self._stopping = asyncio.Event()
        # One piece of work per message at a time, so the next loop can't repeat it.
        self._in_flight: dict[int, asyncio.Task[None]] = {}
        # Tasks waiting for a slot. They haven't claimed anything, so they're safe to cancel.
        self._waiting: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        """Run until `stop()` is called."""
        while not self._stopping.is_set():
            try:
                await self.start_due_work()
            except Exception:
                logger.exception("scheduler_loop_failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass

    async def run_once(self) -> None:
        """One pass, waiting for everything it started. Used by tests."""
        await self.start_due_work()
        if self._in_flight:
            await asyncio.gather(*self._in_flight.values())

    async def stop(self) -> None:
        """Stop taking new work and finish sends already in flight (contracts/runtime-config.md)."""
        self._stopping.set()
        for task in self._waiting:
            task.cancel()
        if self._in_flight:
            await asyncio.wait(self._in_flight.values(), timeout=SHUTDOWN_GRACE_SECONDS)

    async def start_due_work(self) -> None:
        self.heartbeat_path.touch()
        now = self.clock.now()
        # Due messages go first: one that's due during its own retry only advances its
        # schedule, so an outage ends in a single send.
        for due in await self.repo.due_messages(now, BATCH_SIZE):
            message_id = due.message_id
            self._start(
                message_id, due.user_id, lambda m=message_id: self.repo.claim(m, self.clock.now())
            )
        for retry in await self.repo.due_retries(now, BATCH_SIZE):
            delivery_id = retry.delivery_id
            self._start(
                retry.message_id,
                retry.user_id,
                lambda d=delivery_id: self.repo.claim_retry(d, self.clock.now()),
            )

    def _start(
        self, message_id: int, user_id: int, claim: Callable[[], Awaitable[Claim | None]]
    ) -> None:
        if message_id in self._in_flight or self._stopping.is_set():
            return
        task = asyncio.create_task(self._deliver(user_id, claim))
        self._in_flight[message_id] = task
        task.add_done_callback(lambda _: self._in_flight.pop(message_id, None))

    async def _deliver(self, user_id: int, claim: Callable[[], Awaitable[Claim | None]]) -> None:
        task = asyncio.current_task()
        self._waiting.add(task)
        try:
            await self.limiter.acquire(user_id)
        finally:
            self._waiting.discard(task)
        if self._stopping.is_set():
            return
        try:
            claimed = await claim()
            if claimed is not None:
                await self._send(claimed)
        except Exception:
            logger.exception("delivery_failed user=%s", user_id)

    async def _send(self, claim: Claim) -> None:
        delivery, user = claim.delivery_id, claim.user_id
        try:
            if self.clock.now() - claim.scheduled_at > OVERDUE_NOTE_AFTER:
                note = translate(
                    claim.language, "overdue_note", when=format_when(claim.scheduled_at)
                )
                await self.bot.send_message(user, note)
                await self.limiter.acquire(user)
            await self.bot.send_message(user, claim.text)
        except TelegramRetryAfter as error:
            self.limiter.pause(error.retry_after)
            await self._retry(claim, error, error.retry_after)
        except TelegramForbiddenError:
            logger.info("send_blocked delivery=%s user=%s", delivery, user)
            await self.repo.record_blocked(claim, self.clock.now())
        except (TelegramGatewayError, RestartingTelegram, TelegramUnauthorizedError) as error:
            # Rejected before delivery. Unauthorized means the token needs fixing.
            await self._retry(claim, error)
        except TelegramNetworkError as error:
            if _connection_never_made(error):
                await self._retry(claim, error)
            else:
                await self._unknown(claim, error)
        except TelegramServerError as error:
            await self._unknown(claim, error)
        except TelegramAPIError as error:
            name = type(error).__name__
            logger.warning("send_failed delivery=%s user=%s error=%s", delivery, user, name)
            await self.repo.record_failed(delivery, self.clock.now(), name)
        except Exception as error:
            await self._unknown(claim, error)
        else:
            logger.info("send_ok delivery=%s user=%s", delivery, user)
            await self.repo.record_sent(delivery, self.clock.now())

    async def _retry(self, claim: Claim, error: Exception, retry_after: int | None = None) -> None:
        name = type(error).__name__
        logger.warning(
            "send_retry delivery=%s user=%s error=%s", claim.delivery_id, claim.user_id, name
        )
        await self.repo.record_retry(claim.delivery_id, self.clock.now(), name, retry_after)

    async def _unknown(self, claim: Claim, error: Exception) -> None:
        name = type(error).__name__
        logger.warning(
            "send_unknown delivery=%s user=%s error=%s", claim.delivery_id, claim.user_id, name
        )
        await self.repo.record_unknown(claim.delivery_id, self.clock.now(), name)
