import asyncio
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    RestartingTelegram,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage

from conftest import USER, FakeSession, Harness
from reminder_bot.bot.session import TelegramGatewayError
from reminder_bot.clock import FixedClock
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter
from reminder_bot.storage.repositories import Message, Repository

# 14:45 in Kyiv on 7 November 2026.
DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)
TODAY = date(2026, 11, 7)
SEND_TIME = time(14, 45)


class InstantSleep:
    """Lets the limiter run without real waiting, and records what it would wait."""

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
        bot=Bot("123456:TEST", session=session),
        clock=clock,
        limiter=RateLimiter(clock, sleep),
        heartbeat_path=tmp_path / "heartbeat",
    )


async def make(
    repo: Repository,
    clock: FixedClock,
    recurrence: Recurrence = Recurrence.ONCE,
    interval_days: int | None = None,
    start: date = TODAY,
    user_id: int = USER,
    text: str = "Pay rent",
) -> Message:
    await repo.get_or_create_user(user_id, "en", clock.now())
    rule = Rule(recurrence, start, SEND_TIME, interval_days)
    return await repo.create_message(user_id, text, rule, clock.now())


async def get(repo: Repository, message: Message) -> Message:
    return await repo.get_message(message.user_id, message.id)


async def deliveries(repo: Repository, message: Message) -> list:
    return await repo._db.fetch_all(
        "SELECT * FROM deliveries WHERE message_id = ? ORDER BY id", (message.id,)
    )


def texts(session: FakeSession) -> list[str]:
    return session.sent_texts()


async def test_nothing_is_sent_before_its_time(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    clock.set(DUE - timedelta(seconds=1))
    await dispatcher.run_once()
    assert texts(session) == []


async def test_one_time_message_is_sent_once_and_completes(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    await dispatcher.run_once()
    assert texts(session) == ["Pay rent"]
    assert session.calls[0].chat_id == USER
    stored = await get(repo, message)
    assert stored.status == "completed"
    assert stored.next_send_at is None
    assert (await deliveries(repo, message))[0]["status"] == "sent"
    clock.advance(days=1)
    await dispatcher.run_once()
    assert texts(session) == ["Pay rent"]


async def test_text_is_sent_with_no_parse_mode(repo, clock, session, dispatcher) -> None:
    await make(repo, clock, text="*not bold* <b>")
    clock.set(DUE)
    await dispatcher.run_once()
    call = session.calls[0]
    assert call.text == "*not bold* <b>"
    # The bot's default parse mode is what applies, and it must be none.
    assert session.prepare_value(call.parse_mode, bot=dispatcher.bot, files={}) is None


async def test_recurring_message_advances_and_stays_active(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock, Recurrence.INTERVAL, 10)
    clock.set(DUE)
    await dispatcher.run_once()
    stored = await get(repo, message)
    assert stored.status == "active"
    assert stored.next_send_at == DUE + timedelta(days=10)
    clock.advance(days=10)
    await dispatcher.run_once()
    assert texts(session) == ["Pay rent", "Pay rent"]


async def test_message_is_not_sent_twice_when_the_loop_runs_again(
    repo, clock, session, dispatcher
) -> None:
    await make(repo, clock, Recurrence.DAILY)
    clock.set(DUE)
    await dispatcher.run_once()
    await dispatcher.run_once()
    assert len(texts(session)) == 1


async def test_second_claim_for_the_same_send_returns_nothing(repo, clock) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    assert await repo.claim(message.id, clock.now()) is not None
    assert await repo.claim(message.id, clock.now()) is None


async def test_duplicate_delivery_record_blocks_the_send(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock, Recurrence.DAILY)
    await repo._db.execute(
        "INSERT INTO deliveries (message_id, scheduled_at, status, created_at)"
        " VALUES (?, '2026-11-07T12:45:00Z', 'sent', '2026-11-07T12:45:00Z')",
        (message.id,),
    )
    clock.set(DUE)
    await dispatcher.run_once()
    assert texts(session) == []


async def test_missed_sends_collapse_into_one_with_a_note(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock, Recurrence.DAILY)
    clock.set(DUE + timedelta(days=3, hours=2))  # Three daily sends were missed.
    await dispatcher.run_once()
    sent = texts(session)
    assert len(sent) == 2
    assert "7.11.2026 14:45" in sent[0]
    assert "Kyiv time" in sent[0]
    assert sent[1] == "Pay rent"
    stored = await get(repo, message)
    assert stored.next_send_at == DUE + timedelta(days=4)
    await dispatcher.run_once()
    assert len(texts(session)) == 2


async def test_no_note_up_to_one_minute_late(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    clock.set(DUE + timedelta(seconds=60))
    await dispatcher.run_once()
    assert texts(session) == ["Pay rent"]


async def test_note_when_more_than_one_minute_late(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    clock.set(DUE + timedelta(seconds=61))
    await dispatcher.run_once()
    assert len(texts(session)) == 2
    assert texts(session)[-1] == "Pay rent"


async def test_note_is_in_the_users_language(repo, clock, session, dispatcher) -> None:
    await repo.get_or_create_user(USER, "uk", clock.now())
    await make(repo, clock)
    clock.set(DUE + timedelta(hours=1))
    await dispatcher.run_once()
    assert "за Києвом" in texts(session)[0]


async def test_blocked_users_are_skipped(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    await repo.set_blocked(USER, clock.now())
    clock.set(DUE)
    await dispatcher.run_once()
    assert session.calls == []


# The failure table in research.md


def retry_after(method):
    return TelegramRetryAfter(method=method, message="flood", retry_after=120)


def connect_error(method):
    return TelegramNetworkError(method=method, message="ClientConnectorError: refused")


def gateway_error(method):
    return TelegramGatewayError(method=method, message="HTTP 502")


def restarting_error(method):
    return RestartingTelegram(method=method, message="restart")


def read_timeout(method):
    return TelegramNetworkError(method=method, message="Request timeout error")


def disconnect(method):
    return TelegramNetworkError(method=method, message="ServerDisconnectedError: gone")


def server_500(method):
    return TelegramServerError(method=method, message="Internal Server Error")


def bad_request(method):
    return TelegramBadRequest(method=method, message="Bad Request: chat not found")


def forbidden(method):
    return TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")


def unexpected(method):
    return RuntimeError("something unexpected")


async def test_flood_limit_saves_a_retry_at_retry_after(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(retry_after)
    await dispatcher.run_once()
    row = (await deliveries(repo, message))[0]
    assert row["status"] == "retrying"
    assert row["next_attempt_at"] == "2026-11-07T12:47:00Z"
    stored = await get(repo, message)
    assert stored.status == "active"
    assert stored.next_send_at is None


@pytest.mark.parametrize("error", [connect_error, gateway_error, restarting_error])
async def test_safe_errors_are_retried_and_then_delivered(
    repo, clock, session, dispatcher, error
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(error)
    await dispatcher.run_once()
    assert (await deliveries(repo, message))[0]["status"] == "retrying"
    assert (await get(repo, message)).status == "active"

    # Not retried before its time.
    await dispatcher.run_once()
    assert len(session.calls) == 1

    clock.advance(seconds=30)
    await dispatcher.run_once()
    row = (await deliveries(repo, message))[0]
    assert row["status"] == "sent"
    assert (await get(repo, message)).status == "completed"
    assert texts(session)[-1] == "Pay rent"


async def test_backoff_doubles_up_to_five_minutes(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    delays = []
    for _ in range(7):
        session.errors.append(connect_error)
        before = clock.now()
        await dispatcher.run_once()
        row = (await deliveries(repo, message))[0]
        attempt_at = datetime.strptime(row["next_attempt_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        delays.append((attempt_at - before).total_seconds())
        clock.set(attempt_at)
    assert delays == [30, 60, 120, 240, 300, 300, 300]


async def test_retries_continue_past_one_hour(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    for _ in range(40):  # Over 3 hours at the 5-minute cap.
        session.errors.append(gateway_error)
        await dispatcher.run_once()
        clock.advance(minutes=5)
    assert (await deliveries(repo, message))[0]["status"] == "retrying"
    await dispatcher.run_once()
    assert (await deliveries(repo, message))[0]["status"] == "sent"
    assert (await get(repo, message)).status == "completed"


async def test_retry_after_a_long_outage_includes_the_note(
    repo, clock, session, dispatcher
) -> None:
    await make(repo, clock)
    clock.set(DUE)
    session.errors.append(gateway_error)
    await dispatcher.run_once()
    clock.advance(hours=2)
    await dispatcher.run_once()
    sent = [t for t in texts(session) if t != "Pay rent"]
    assert sent and "7.11.2026 14:45" in sent[-1]
    assert texts(session)[-1] == "Pay rent"


async def test_retrying_send_resumes_after_a_restart(
    repo, clock, session, dispatcher, tmp_path, sleep
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(connect_error)
    await dispatcher.run_once()

    # A new process starts. Only `sending` records are treated as interrupted.
    assert await repo.mark_leftover_sends_unknown(clock.now()) == 0
    restarted = MessageDispatcher(
        repo=repo,
        bot=Bot("123456:TEST", session=session),
        clock=clock,
        limiter=RateLimiter(clock, sleep),
        heartbeat_path=tmp_path / "heartbeat",
    )
    clock.advance(minutes=1)
    await restarted.run_once()
    assert (await deliveries(repo, message))[0]["status"] == "sent"


@pytest.mark.parametrize("error", [server_500, read_timeout, disconnect, unexpected])
async def test_unknown_outcomes_are_not_retried(repo, clock, session, dispatcher, error) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(error)
    await dispatcher.run_once()
    assert (await deliveries(repo, message))[0]["status"] == "unknown"
    stored = await get(repo, message)
    assert stored.status == "completed"
    assert not stored.not_delivered
    clock.advance(days=1)
    await dispatcher.run_once()
    assert len(session.calls) == 1


async def test_other_4xx_fails_and_shows_as_not_delivered(repo, clock, session, dispatcher) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(bad_request)
    await dispatcher.run_once()
    assert (await deliveries(repo, message))[0]["status"] == "failed"
    stored = await get(repo, message)
    assert stored.status == "completed"
    assert stored.not_delivered


async def test_recurring_message_continues_after_a_permanent_failure(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock, Recurrence.DAILY)
    clock.set(DUE)
    session.errors.append(bad_request)
    await dispatcher.run_once()
    stored = await get(repo, message)
    assert stored.status == "active"
    assert not stored.not_delivered
    assert stored.next_send_at == DUE + timedelta(days=1)


async def test_403_blocks_the_user_and_one_time_message_keeps_its_time(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(forbidden)
    await dispatcher.run_once()
    assert (await repo.get_user(USER)).blocked_at == DUE
    stored = await get(repo, message)
    assert stored.status == "active"
    assert stored.next_send_at == DUE
    assert (await deliveries(repo, message))[0]["status"] == "blocked"


async def test_leftover_sending_records_become_unknown_and_are_not_resent(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    await repo.claim(message.id, clock.now())  # The process dies right here.
    assert await repo.mark_leftover_sends_unknown(clock.now()) == 1
    assert (await deliveries(repo, message))[0]["status"] == "unknown"
    assert (await get(repo, message)).status == "completed"
    await dispatcher.run_once()
    assert session.calls == []


async def test_recurring_message_due_during_a_retry_adds_no_new_delivery(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock, Recurrence.DAILY)
    clock.set(DUE)
    session.errors.append(gateway_error)
    await dispatcher.run_once()

    # The outage lasts past the next daily send. Keep every retry failing.
    for _ in range(300):
        clock.advance(minutes=5)
        session.errors.append(gateway_error)
        await dispatcher.run_once()
    assert len(await deliveries(repo, message)) == 1

    # Service returns: one message is sent, and the schedule is still ahead.
    clock.advance(minutes=5)
    session.calls.clear()
    session.errors.clear()
    await dispatcher.run_once()
    if not texts(session):  # A daily send fell due this pass, which only moved the schedule.
        await dispatcher.run_once()
    assert texts(session).count("Pay rent") == 1
    assert (await deliveries(repo, message))[0]["status"] == "sent"
    assert (await get(repo, message)).next_send_at > clock.now()


# Editing at send time (spec edge case)


async def test_text_edited_during_a_retry_is_sent_in_its_new_form_only(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(connect_error)
    await dispatcher.run_once()
    await repo.update_text(USER, message.id, "New text", clock.now())
    clock.advance(seconds=30)
    await dispatcher.run_once()
    assert texts(session)[-1] == "New text"
    assert len(await deliveries(repo, message)) == 1


async def test_message_removed_during_a_retry_is_never_sent(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(connect_error)
    await dispatcher.run_once()
    session.calls.clear()
    await repo.delete_message(USER, message.id)
    clock.advance(minutes=5)
    await dispatcher.run_once()
    assert session.calls == []


async def test_message_rescheduled_during_a_retry_uses_only_the_new_time(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    session.errors.append(connect_error)
    await dispatcher.run_once()
    session.calls.clear()

    new_rule = Rule(Recurrence.ONCE, date(2026, 11, 9), SEND_TIME)
    await repo.update_schedule(USER, message.id, new_rule, clock.now())
    clock.advance(minutes=5)
    await dispatcher.run_once()
    assert session.calls == []

    clock.set(datetime(2026, 11, 9, 12, 45, tzinfo=UTC))
    await dispatcher.run_once()
    assert texts(session) == ["Pay rent"]
    assert (await get(repo, message)).status == "completed"


async def test_rescheduling_while_a_send_is_in_flight_keeps_the_new_schedule(repo, clock) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    claim = await repo.claim(message.id, clock.now())
    new_rule = Rule(Recurrence.ONCE, date(2026, 11, 9), SEND_TIME)
    await repo.update_schedule(USER, message.id, new_rule, clock.now())
    await repo.record_sent(claim.delivery_id, clock.now())
    stored = await get(repo, message)
    assert stored.status == "active"
    assert stored.next_send_at == datetime(2026, 11, 9, 12, 45, tzinfo=UTC)


async def test_message_removed_just_before_claim_is_not_sent(
    repo, clock, session, dispatcher
) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    await repo.delete_message(USER, message.id)
    await dispatcher.run_once()
    assert session.calls == []


async def test_removing_after_claim_still_records_cleanly(repo, clock) -> None:
    message = await make(repo, clock)
    clock.set(DUE)
    claim = await repo.claim(message.id, clock.now())
    await repo.delete_message(USER, message.id)
    await repo.record_sent(claim.delivery_id, clock.now())
    assert await get(repo, message) is None


# Rate limiting


async def test_limiter_spaces_one_chat_about_a_second_apart(clock, sleep) -> None:
    limiter = RateLimiter(clock, sleep)
    for _ in range(3):
        await limiter.acquire(USER)
    assert sleep.waits == pytest.approx([1.0, 2.0])


async def test_limiter_holds_overall_rate_to_25_per_second(clock, sleep) -> None:
    limiter = RateLimiter(clock, sleep)
    for user_id in range(26):
        await limiter.acquire(user_id)
    assert sleep.waits[-1] == pytest.approx(1.0)


async def test_flood_response_pauses_all_sending(repo, clock, session, dispatcher, sleep) -> None:
    await make(repo, clock, user_id=1)
    await make(repo, clock, user_id=2)
    clock.set(DUE)
    session.errors.append(retry_after)
    await dispatcher.run_once()
    await make(repo, clock, Recurrence.ONCE, start=date(2026, 11, 8), user_id=3)
    await dispatcher.limiter.acquire(3)
    assert sleep.waits[-1] == pytest.approx(120, abs=1)


# Loop behavior


async def test_heartbeat_file_is_updated(repo, clock, dispatcher, tmp_path) -> None:
    await dispatcher.run_once()
    assert (tmp_path / "heartbeat").exists()


async def test_shutdown_leaves_unclaimed_messages_due(repo, clock, session, tmp_path) -> None:
    message = await make(repo, clock)
    clock.set(DUE)

    async def sleep_forever(seconds: float) -> None:
        await asyncio.Event().wait()

    dispatcher = MessageDispatcher(
        repo=repo,
        bot=Bot("123456:TEST", session=session),
        clock=clock,
        limiter=RateLimiter(clock, sleep_forever),
        heartbeat_path=tmp_path / "heartbeat",
    )
    await dispatcher.limiter.acquire(0)  # Uses up the limiter so the next send must wait.
    await dispatcher.start_due_work()
    await dispatcher.stop()
    assert session.calls == []
    stored = await get(repo, message)
    assert stored.next_send_at == DUE
    assert await deliveries(repo, message) == []


async def test_send_method_is_send_message(repo, clock, session, dispatcher) -> None:
    await make(repo, clock)
    clock.set(DUE)
    await dispatcher.run_once()
    assert isinstance(session.calls[0], SendMessage)


async def test_harness_and_dispatcher_share_the_same_data(
    harness: Harness, dispatcher: MessageDispatcher, clock, session
) -> None:
    chat = harness.chat()
    await chat.send("/new")
    await chat.send("From the flow")
    await chat.press("rec:once")
    await chat.send("7.11.2026")
    await chat.send("14:45")
    clock.set(DUE)
    await dispatcher.run_once()
    assert texts(session)[-1] == "From the flow"
