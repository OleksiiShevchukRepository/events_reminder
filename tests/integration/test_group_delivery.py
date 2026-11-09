"""Sending group reminders, and what happens when a group can't be reached (002 US1, FR-115,
FR-116, research §9 to §11)."""

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramNotFound

from conftest import (
    BOT_ID,
    GROUP,
    OTHER_GROUP,
    USER,
    FakeSession,
    cannot_post,
    chat_gone,
    forbidden,
    upgraded_to,
)
from reminder_bot.clock import FixedClock
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter
from reminder_bot.scheduler.maintenance import Maintenance
from reminder_bot.storage.db import Database
from reminder_bot.storage.repositories import Message, Repository

DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)  # 14:45 in Kyiv.
TODAY = date(2026, 11, 7)
NEW_GROUP = -1009999


class InstantSleep:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


@pytest.fixture
def sleep() -> InstantSleep:
    return InstantSleep()


@pytest.fixture
def dispatcher(
    repo: Repository, clock: FixedClock, session: FakeSession, sleep: InstantSleep, tmp_path: Path
) -> MessageDispatcher:
    return MessageDispatcher(
        repo=repo,
        bot=Bot(f"{BOT_ID}:TEST", session=session),
        clock=clock,
        limiter=RateLimiter(clock, sleep),
        heartbeat_path=tmp_path / "heartbeat",
    )


async def make(
    repo: Repository,
    clock: FixedClock,
    recurrence: Recurrence = Recurrence.ONCE,
    chat_id: int = GROUP,
    text: str = "Bins out",
) -> Message:
    kind = "group" if chat_id < 0 else "private"
    await repo.get_or_create_chat(chat_id, "en", clock.now(), kind=kind)
    rule = Rule(recurrence, TODAY, time(14, 45))
    name = "Anna" if chat_id < 0 else None
    return await repo.create_message(chat_id, text, rule, clock.now(), name)


# Sending


async def test_group_reminder_goes_to_the_group_in_general_with_no_names(
    repo, clock, session, dispatcher
) -> None:
    await make(repo, clock)
    clock.set(DUE)
    await dispatcher.run_once()
    [send] = session.sent()
    assert send.chat_id == GROUP
    assert send.message_thread_id is None
    assert send.text == "Bins out"


async def test_late_group_reminder_gets_the_note(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    clock.set(DUE + timedelta(minutes=10))
    await dispatcher.run_once()
    note, text = session.sent_texts(GROUP)
    assert "was due" in note
    assert text == "Bins out"


async def test_limiter_spaces_one_group_three_seconds_apart(clock, sleep) -> None:
    limiter = RateLimiter(clock, sleep)
    for _ in range(3):
        await limiter.acquire(GROUP)
    assert sleep.waits == pytest.approx([3.0, 6.0])
    sleep.waits.clear()
    private = RateLimiter(clock, sleep)
    for _ in range(2):
        await private.acquire(USER)
    assert sleep.waits == pytest.approx([1.0])


async def test_fifteen_group_reminders_due_together_finish_within_45_seconds(
    repo, clock, session, dispatcher, sleep
) -> None:
    for index in range(15):
        await make(repo, clock, Recurrence.DAILY, text=f"Reminder {index}")
    clock.set(DUE)
    await dispatcher.run_once()
    assert len(session.sent(GROUP)) == 15
    assert max(sleep.waits) <= 45


async def test_twenty_five_due_together_are_all_sent(repo, clock, session, dispatcher) -> None:
    for index in range(25):
        await make(repo, clock, Recurrence.DAILY, text=f"Reminder {index}")
    clock.set(DUE)
    await dispatcher.run_once()
    assert len(session.sent(GROUP)) == 25


# Unreachable groups


@pytest.mark.parametrize("error", [forbidden, cannot_post, chat_gone])
async def test_a_group_the_bot_cant_post_in_becomes_unreachable(
    repo, clock, session, dispatcher, error
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(error)
    await dispatcher.run_once()
    assert (await repo.get_chat(GROUP)).unreachable_at == DUE
    # The one-time reminder keeps its time, and nothing more is attempted while unreachable.
    assert (await repo.get_message(GROUP, message.id)).next_send_at == DUE
    session.calls.clear()
    clock.advance(minutes=10)
    await dispatcher.run_once()
    assert session.sent() == []


async def test_bad_request_in_a_private_chat_is_still_a_failure(
    repo, clock, session, dispatcher
) -> None:
    await make(repo, clock, chat_id=USER)
    clock.set(DUE)
    session.errors.append(chat_gone)
    await dispatcher.run_once()
    assert (await repo.get_chat(USER)).unreachable_at is None


async def test_other_api_errors_are_recorded_as_failed(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock, chat_id=USER)
    clock.set(DUE)
    session.errors.append(lambda method: TelegramNotFound(method, "Not Found"))
    await dispatcher.run_once()
    [delivery] = await repo._db.fetch_all(
        "SELECT status, error FROM deliveries WHERE message_id = ?", (message.id,)
    )
    assert (delivery["status"], delivery["error"]) == ("failed", "TelegramNotFound")


async def test_other_groups_keep_receiving(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    await make(repo, clock, chat_id=OTHER_GROUP, text="Other")
    clock.set(DUE)
    await repo.set_unreachable(GROUP, clock.now())
    await dispatcher.run_once()
    assert session.sent_texts() == ["Other"]


# Supergroup upgrade


async def test_upgrade_found_while_sending_moves_the_group_and_sends_once(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(upgraded_to(NEW_GROUP))
    await dispatcher.run_once()
    assert await repo.get_chat(GROUP) is None
    assert (await repo.get_chat(NEW_GROUP)).kind == "group"
    assert await repo.get_message(NEW_GROUP, message.id) is not None
    clock.advance(seconds=5)
    await dispatcher.run_once()
    assert session.sent_texts(NEW_GROUP) == ["Bins out"]
    clock.advance(minutes=10)
    await dispatcher.run_once()
    assert session.sent_texts(NEW_GROUP) == ["Bins out"]


async def test_moving_twice_does_nothing_the_second_time(repo, clock) -> None:
    message = await make(repo, clock)
    assert await repo.move_chat(GROUP, NEW_GROUP) is True
    assert await repo.move_chat(GROUP, NEW_GROUP) is False
    assert (await repo.get_message(NEW_GROUP, message.id)).text == "Bins out"


# Deletion after 12 months


async def test_a_group_unreachable_for_12_months_is_deleted(
    db: Database, repo, clock, tmp_path
) -> None:
    message = await make(repo, clock)
    await make(repo, clock, chat_id=OTHER_GROUP)
    await repo.set_unreachable(GROUP, clock.now())
    clock.advance(days=200)
    await repo.set_unreachable(OTHER_GROUP, clock.now())
    clock.advance(days=170)
    await Maintenance(db, repo, clock, tmp_path / "backups").run()
    assert await repo.get_chat(GROUP) is None
    assert await repo.get_message(GROUP, message.id) is None
    assert await repo.get_chat(OTHER_GROUP) is not None
