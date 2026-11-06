import logging
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
)

from conftest import FakeSession, Harness
from reminder_bot.clock import FixedClock
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter
from reminder_bot.storage.repositories import Repository

SECRET_TEXT = "my-private-reminder-text"
SECRET_TOKEN = "123456:SECRET-TOKEN"
DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)


async def create(harness: Harness, text: str, user_id: int) -> None:
    chat = harness.chat(user_id=user_id)
    await chat.send("/new")
    await chat.send(text)
    await chat.press("rec:once")
    await chat.send("7.11.2026")
    await chat.send("14:45")


async def test_no_reminder_text_or_token_in_logs(
    caplog,
    harness: Harness,
    repo: Repository,
    clock: FixedClock,
    session: FakeSession,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.DEBUG)

    async def instant(_: float) -> None:
        pass

    dispatcher = MessageDispatcher(
        repo=repo,
        bot=Bot(SECRET_TOKEN, session=session),
        clock=clock,
        limiter=RateLimiter(clock, instant),
        heartbeat_path=tmp_path / "heartbeat",
    )

    # One send of each kind: success, retry, unknown, permanent failure and blocked.
    errors = [
        None,
        lambda method: TelegramNetworkError(method=method, message="ClientConnectorError: x"),
        lambda method: TelegramNetworkError(method=method, message="Request timeout error"),
        lambda method: TelegramBadRequest(method=method, message="Bad Request"),
        lambda method: TelegramForbiddenError(method=method, message="Forbidden"),
    ]
    for index, error in enumerate(errors):
        await create(harness, f"{SECRET_TEXT}-{index}", user_id=100 + index)
        clock.set(DUE)
        session.calls.clear()
        if error:
            session.errors.append(error)
        await dispatcher.run_once()
        clock.set(datetime(2026, 11, 6, 12, 0, tzinfo=UTC))

    assert caplog.records, "the flow should have logged something"
    assert SECRET_TEXT not in caplog.text
    assert SECRET_TOKEN not in caplog.text
    assert "SECRET-TOKEN" not in caplog.text
