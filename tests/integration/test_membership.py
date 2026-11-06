from datetime import UTC, date, datetime, time, timedelta

from conftest import USER, Harness
from reminder_bot.domain.schedule import Recurrence, Rule

DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)
RULE_ONCE = Rule(Recurrence.ONCE, date(2026, 11, 7), time(14, 45))
RULE_DAILY = Rule(Recurrence.DAILY, date(2026, 11, 7), time(14, 45))


async def test_kicked_sets_and_member_clears_blocked_at(harness: Harness) -> None:
    chat = harness.chat()
    await chat.send("/start")
    await chat.set_status("kicked")
    assert (await harness.repo.get_user(USER)).blocked_at == harness.clock.now()
    await chat.set_status("member")
    assert (await harness.repo.get_user(USER)).blocked_at is None


async def test_status_change_from_an_unknown_user_stores_nothing(harness: Harness) -> None:
    await harness.chat().set_status("kicked")
    assert await harness.repo.get_user(USER) is None


async def test_blocked_at_keeps_the_original_date_on_a_repeat_event(harness: Harness) -> None:
    chat = harness.chat()
    await chat.send("/start")
    await chat.set_status("kicked")
    first = harness.clock.now()
    harness.clock.advance(days=1)
    await chat.set_status("kicked")
    assert (await harness.repo.get_user(USER)).blocked_at == first


async def test_unblock_moves_recurring_messages_ahead_with_no_catch_up(harness: Harness) -> None:
    repo, clock = harness.repo, harness.clock
    chat = harness.chat()
    await chat.send("/start")
    message = await repo.create_message(USER, "x", RULE_DAILY, clock.now())
    await chat.set_status("kicked")
    clock.set(DUE + timedelta(days=5, hours=1))
    await chat.set_status("member")
    stored = await repo.get_message(USER, message.id)
    assert stored.next_send_at == DUE + timedelta(days=6)
    assert await repo.due_messages(clock.now(), 10) == []


async def test_future_recurring_send_is_unchanged_by_an_unblock(harness: Harness) -> None:
    repo, clock = harness.repo, harness.clock
    chat = harness.chat()
    await chat.send("/start")
    message = await repo.create_message(USER, "x", RULE_DAILY, clock.now())
    await chat.set_status("kicked")
    await chat.set_status("member")
    assert (await repo.get_message(USER, message.id)).next_send_at == DUE


async def test_overdue_one_time_message_stays_due_after_an_unblock(harness: Harness) -> None:
    repo, clock = harness.repo, harness.clock
    chat = harness.chat()
    await chat.send("/start")
    message = await repo.create_message(USER, "x", RULE_ONCE, clock.now())
    await chat.set_status("kicked")
    clock.set(DUE + timedelta(days=5))
    assert await repo.due_messages(clock.now(), 10) == []
    await chat.set_status("member")
    due = await repo.due_messages(clock.now(), 10)
    assert [item.message_id for item in due] == [message.id]
    assert (await repo.get_message(USER, message.id)).next_send_at == DUE


async def test_one_time_message_returned_by_a_403_can_be_claimed_again(harness: Harness) -> None:
    repo, clock = harness.repo, harness.clock
    await repo.get_or_create_user(USER, "en", clock.now())
    message = await repo.create_message(USER, "x", RULE_ONCE, clock.now())
    clock.set(DUE)
    claim = await repo.claim(message.id, clock.now())
    await repo.record_blocked(claim, clock.now())
    assert await repo.claim(message.id, clock.now()) is None  # Still blocked.

    await repo.unblock(USER, clock.now())
    again = await repo.claim(message.id, clock.now())
    assert again is not None
    assert again.scheduled_at == DUE


async def test_recurring_retry_is_dropped_on_unblock_as_a_catch_up(harness: Harness) -> None:
    repo, clock = harness.repo, harness.clock
    await repo.get_or_create_user(USER, "en", clock.now())
    message = await repo.create_message(USER, "x", RULE_DAILY, clock.now())
    clock.set(DUE)
    claim = await repo.claim(message.id, clock.now())
    await repo.record_retry(claim.delivery_id, clock.now(), "connect")
    await repo.set_blocked(USER, clock.now())
    clock.advance(hours=1)
    assert await repo.due_retries(clock.now(), 10) == []
    await repo.unblock(USER, clock.now())
    assert await repo.due_retries(clock.now(), 10) == []


async def test_one_time_retry_survives_a_block_and_resumes(harness: Harness) -> None:
    repo, clock = harness.repo, harness.clock
    await repo.get_or_create_user(USER, "en", clock.now())
    message = await repo.create_message(USER, "x", RULE_ONCE, clock.now())
    clock.set(DUE)
    claim = await repo.claim(message.id, clock.now())
    await repo.record_retry(claim.delivery_id, clock.now(), "connect")
    await repo.set_blocked(USER, clock.now())
    clock.advance(hours=1)
    assert await repo.due_retries(clock.now(), 10) == []
    await repo.unblock(USER, clock.now())
    assert [r.message_id for r in await repo.due_retries(clock.now(), 10)] == [message.id]


async def test_sending_a_message_to_the_bot_clears_a_missed_block(harness: Harness) -> None:
    chat = harness.chat()
    await chat.send("/start")
    await harness.repo.set_blocked(USER, harness.clock.now())
    await chat.send("/help")
    assert (await harness.repo.get_user(USER)).blocked_at is None
