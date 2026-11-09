from collections import Counter
from datetime import UTC, date, datetime, time
from pathlib import Path

from aiogram import Bot

from conftest import FakeSession
from reminder_bot.clock import FixedClock
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter
from reminder_bot.storage.repositories import Repository

PEAK_PER_MINUTE = 1500
DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)


async def test_peak_minute_is_all_sent_within_one_minute_of_simulated_time(
    repo: Repository, clock: FixedClock, session: FakeSession, tmp_path: Path
) -> None:
    """Simulated time: the limiter's waits are recorded instead of slept (SC-002)."""
    waits: list[float] = []

    async def record_wait(seconds: float) -> None:
        waits.append(seconds)

    rule = Rule(Recurrence.ONCE, date(2026, 11, 7), time(14, 45))
    for user_id in range(PEAK_PER_MINUTE):
        await repo.get_or_create_chat(user_id, "en", clock.now())
        await repo.create_message(user_id, f"Message {user_id}", rule, clock.now())

    dispatcher = MessageDispatcher(
        repo=repo,
        bot=Bot("123456:TEST", session=session),
        clock=clock,
        limiter=RateLimiter(clock, record_wait),
        heartbeat_path=tmp_path / "heartbeat",
    )
    clock.set(DUE)
    await dispatcher.run_once()

    delivered = Counter(call.chat_id for call in session.sent())
    assert len(delivered) == PEAK_PER_MINUTE
    assert set(delivered.values()) == {1}
    assert max(waits) <= 60
    # The limiter is what keeps this at Telegram's limit, so it must really be spacing sends.
    assert max(waits) > 50
