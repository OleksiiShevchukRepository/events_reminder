from datetime import UTC, date, datetime, time, timedelta

import pytest

from conftest import OTHER_USER, USER, FakeChat, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]
# It's 14:00 in Kyiv on 6 November 2026 (see conftest).
KYIV_1445_ON_7TH = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)


def utc_from_kyiv(day: int, hour: int, minute: int, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour - 2, minute, tzinfo=UTC)


async def add(
    harness: Harness,
    recurrence: Recurrence = Recurrence.WEEKLY,
    start: date = date(2026, 11, 7),
    interval_days: int | None = None,
    user_id: int = USER,
    text: str = "Original",
):
    await harness.repo.get_or_create_user(user_id, "en", harness.clock.now())
    rule = Rule(recurrence, start, time(14, 45), interval_days)
    return await harness.repo.create_message(user_id, text, rule, harness.clock.now())


async def reload(harness: Harness, message, user_id: int = USER):
    return await harness.repo.get_message(user_id, message.id)


async def test_text_edit_leaves_the_schedule_unchanged(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_text")
    assert chat.last_text == EN["prompt_new_text"]
    await chat.send("New text")
    stored = await reload(harness, message)
    assert stored.text == "New text"
    assert stored.next_send_at == message.next_send_at
    assert stored.rule == message.rule
    assert "New text" in chat.last_text


@pytest.mark.parametrize("bad", ["   ", "a" * 4097])
async def test_invalid_text_leaves_the_message_unchanged(
    chat: FakeChat, harness: Harness, bad: str
) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_text")
    await chat.send(bad)
    assert (await reload(harness, message)).text == "Original"


async def test_time_edit_recalculates_and_keeps_the_start_date(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_time")
    await chat.send("16:00")
    stored = await reload(harness, message)
    assert stored.send_time == time(16, 0)
    assert stored.start_date == date(2026, 11, 7)
    assert stored.next_send_at == utc_from_kyiv(7, 16, 0)
    assert "Kyiv time" in chat.last_text


async def test_time_edit_of_a_running_recurring_message_uses_its_schedule(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.DAILY, date(2026, 11, 1))
    await chat.press(f"msg:{message.id}:edit_time")
    await chat.send("13:00")  # Already past today, so the next send is tomorrow.
    assert (await reload(harness, message)).next_send_at == utc_from_kyiv(7, 13, 0)


async def test_one_time_time_edit_must_be_in_the_future(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, Recurrence.ONCE, date(2026, 11, 6))
    harness_time = await reload(harness, message)
    await chat.press(f"msg:{message.id}:edit_time")
    await chat.send("13:00")
    assert chat.last_text == EN["error_datetime_past"]
    assert (await reload(harness, message)).send_time == harness_time.send_time
    await chat.send("15:00")
    assert (await reload(harness, message)).send_time == time(15, 0)


async def test_invalid_time_leaves_the_message_unchanged(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_time")
    await chat.send("25:70")
    assert chat.last_text == EN["error_time_invalid"]
    assert (await reload(harness, message)).send_time == time(14, 45)


@pytest.mark.parametrize(
    ("recurrence", "expected_next"),
    [
        (Recurrence.DAILY, date(2026, 11, 20)),
        (Recurrence.WEEKLY, date(2026, 11, 20)),
        (Recurrence.MONTHLY, date(2026, 11, 20)),
        (Recurrence.YEARLY, date(2026, 11, 20)),
        (Recurrence.ONCE, date(2026, 11, 20)),
    ],
)
async def test_date_edit_uses_the_first_send_on_the_new_date(
    chat: FakeChat, harness: Harness, recurrence: Recurrence, expected_next: date
) -> None:
    message = await add(harness, recurrence)
    await chat.press(f"msg:{message.id}:edit_date")
    assert chat.last_text == EN["prompt_new_date"]
    await chat.send("20.11.2026")
    stored = await reload(harness, message)
    assert stored.start_date == expected_next
    assert stored.next_send_at == utc_from_kyiv(20, 14, 45)


@pytest.mark.parametrize(
    ("bad_date", "error"),
    [
        ("5.11.2026", "error_date_past"),
        ("31.02.2027", "error_date_invalid"),
        ("1.1.2101", "error_date_too_far"),
    ],
)
async def test_invalid_date_leaves_the_message_unchanged(
    chat: FakeChat, harness: Harness, bad_date: str, error: str
) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_date")
    await chat.send(bad_date)
    assert chat.last_text == EN[error]
    assert (await reload(harness, message)).rule == message.rule


async def test_date_edit_to_today_after_the_time_has_passed_is_rejected(
    harness: Harness, chat: FakeChat
) -> None:
    await harness.repo.get_or_create_user(USER, "en", harness.clock.now())
    rule = Rule(Recurrence.WEEKLY, date(2026, 11, 7), time(9, 0))  # 09:00 is past today.
    message = await harness.repo.create_message(USER, "x", rule, harness.clock.now())
    await chat.press(f"msg:{message.id}:edit_date")
    await chat.send("6.11.2026")
    assert chat.last_text == EN["error_datetime_past"]
    assert (await reload(harness, message)).start_date == date(2026, 11, 7)


async def test_interval_edit_requires_both_date_and_interval(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.INTERVAL, interval_days=10)
    await chat.press(f"msg:{message.id}:edit_date")
    assert chat.last_text == EN["prompt_new_date"]
    await chat.send("25.11.2026")
    # Nothing is saved until both are in.
    assert (await reload(harness, message)).start_date == date(2026, 11, 7)
    assert chat.last_text == EN["prompt_new_interval"]
    await chat.send("5")
    stored = await reload(harness, message)
    assert stored.start_date == date(2026, 11, 25)
    assert stored.interval_days == 5
    assert stored.next_send_at == utc_from_kyiv(25, 14, 45)


async def test_interval_sends_follow_the_new_values_only(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, Recurrence.INTERVAL, interval_days=10)
    await chat.press(f"msg:{message.id}:edit_date")
    await chat.send("25.11.2026")
    await chat.send("5")
    stored = await reload(harness, message)
    from reminder_bot.domain.schedule import next_after

    second = next_after(stored.rule, stored.next_send_at)
    third = next_after(stored.rule, second)
    assert second == utc_from_kyiv(30, 14, 45)
    assert third == datetime(2026, 12, 5, 12, 45, tzinfo=UTC)


async def test_cancelling_part_way_through_an_interval_edit_changes_nothing(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.INTERVAL, interval_days=10)
    await chat.press(f"msg:{message.id}:edit_date")
    await chat.send("25.11.2026")
    await chat.press("flow:cancel")
    assert EN["cancelled"] in chat.texts()
    assert await reload(harness, message) == message


async def test_invalid_interval_in_an_edit_saves_neither_value(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.INTERVAL, interval_days=10)
    await chat.press(f"msg:{message.id}:edit_date")
    await chat.send("25.11.2026")
    await chat.send("0")
    assert chat.last_text == EN["error_interval_invalid"]
    assert await reload(harness, message) == message


@pytest.mark.parametrize("target", [Recurrence.DAILY, Recurrence.MONTHLY, Recurrence.YEARLY])
async def test_recurrence_switch_keeps_start_date_and_asks_nothing_more(
    chat: FakeChat, harness: Harness, target: Recurrence
) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_rec")
    assert chat.last_text == EN["prompt_new_recurrence"]
    await chat.press(f"rec:{target.value}")
    stored = await reload(harness, message)
    assert stored.recurrence is target
    assert stored.start_date == date(2026, 11, 7)
    assert stored.next_send_at == KYIV_1445_ON_7TH
    assert stored.interval_days is None


async def test_weekly_to_monthly_follows_the_monthly_rule_from_the_start_date(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.WEEKLY, date(2026, 10, 7))
    await chat.press(f"msg:{message.id}:edit_rec")
    await chat.press("rec:monthly")
    stored = await reload(harness, message)
    assert stored.next_send_at == KYIV_1445_ON_7TH  # 7 October's monthly date in November.


async def test_switch_to_only_once_asks_for_a_new_date(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, Recurrence.DAILY, date(2026, 11, 1))
    await chat.press(f"msg:{message.id}:edit_rec")
    await chat.press("rec:once")
    assert (await reload(harness, message)).recurrence is Recurrence.DAILY
    assert chat.last_text == EN["prompt_new_date"]
    await chat.send("20.11.2026")
    stored = await reload(harness, message)
    assert stored.recurrence is Recurrence.ONCE
    assert stored.start_date == date(2026, 11, 20)
    assert stored.next_send_at == utc_from_kyiv(20, 14, 45)


async def test_switch_to_only_once_asks_for_a_time_if_the_old_one_has_passed(
    chat: FakeChat, harness: Harness
) -> None:
    await harness.repo.get_or_create_user(USER, "en", harness.clock.now())
    rule = Rule(Recurrence.DAILY, date(2026, 11, 7), time(9, 0))  # 09:00 is past today.
    message = await harness.repo.create_message(USER, "x", rule, harness.clock.now())
    await chat.press(f"msg:{message.id}:edit_rec")
    await chat.press("rec:once")
    await chat.send("6.11.2026")
    assert chat.last_text == EN["prompt_new_time"]
    assert (await reload(harness, message)).recurrence is Recurrence.DAILY
    await chat.send("13:00")
    assert chat.last_text == EN["error_datetime_past"]
    await chat.send("15:00")
    stored = await reload(harness, message)
    assert stored.recurrence is Recurrence.ONCE
    assert stored.next_send_at == utc_from_kyiv(6, 15, 0)


async def test_switch_to_every_n_days_asks_for_interval_and_date(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_rec")
    await chat.press("rec:interval")
    assert chat.last_text == EN["prompt_new_interval"]
    await chat.send("4")
    assert chat.last_text == EN["prompt_new_date"]
    assert (await reload(harness, message)).recurrence is Recurrence.WEEKLY
    await chat.send("20.11.2026")
    stored = await reload(harness, message)
    assert stored.recurrence is Recurrence.INTERVAL
    assert stored.interval_days == 4
    assert stored.next_send_at == utc_from_kyiv(20, 14, 45)


async def test_switch_from_every_n_days_clears_the_interval(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.INTERVAL, interval_days=5)
    await chat.press(f"msg:{message.id}:edit_rec")
    await chat.press("rec:weekly")
    stored = await reload(harness, message)
    assert stored.recurrence is Recurrence.WEEKLY
    assert stored.interval_days is None


@pytest.mark.parametrize("action", ["edit_text", "edit_rec", "edit_date", "edit_time"])
async def test_completed_messages_cannot_be_updated(
    chat: FakeChat, harness: Harness, action: str
) -> None:
    message = await add(harness, Recurrence.ONCE)
    claim = await harness.repo.claim(message.id, message.next_send_at + timedelta(seconds=1))
    await harness.repo.record_sent(claim.delivery_id, message.next_send_at)
    await chat.press(f"msg:{message.id}:{action}")
    assert harness.session.calls[-1].text == EN["no_longer_available"]
    await chat.send("new value")
    assert chat.last_text == EN["unknown_input"]


async def test_message_completed_during_an_edit_is_not_changed(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, Recurrence.ONCE)
    await chat.press(f"msg:{message.id}:edit_text")
    claim = await harness.repo.claim(message.id, message.next_send_at + timedelta(seconds=1))
    await harness.repo.record_sent(claim.delivery_id, message.next_send_at)
    await chat.send("Too late")
    assert (await reload(harness, message)).text == "Original"
    assert chat.last_text == EN["no_longer_available"]


@pytest.mark.parametrize("action", ["edit_text", "edit_rec", "edit_date", "edit_time"])
async def test_another_users_message_cannot_be_updated(
    chat: FakeChat, harness: Harness, action: str
) -> None:
    theirs = await add(harness, user_id=OTHER_USER, text="Theirs")
    await chat.press(f"msg:{theirs.id}:{action}")
    assert harness.session.calls[-1].text == EN["no_longer_available"]
    assert (await reload(harness, theirs, OTHER_USER)) == theirs


async def test_repository_refuses_updates_from_another_user(harness: Harness) -> None:
    theirs = await add(harness, user_id=OTHER_USER)
    now = harness.clock.now()
    assert await harness.repo.update_text(USER, theirs.id, "Hacked", now) is None
    rule = Rule(Recurrence.DAILY, date(2026, 11, 20), time(9, 0))
    assert await harness.repo.update_schedule(USER, theirs.id, rule, now) is None
    assert await reload(harness, theirs, OTHER_USER) == theirs


async def test_each_edit_offers_cancel(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness)
    for action in ("edit_text", "edit_rec", "edit_date", "edit_time"):
        await chat.press(f"msg:{message.id}:{action}")
        assert "Cancel" in chat.last_buttons()
        await chat.press("flow:cancel")
    assert await reload(harness, message) == message


async def test_cancel_command_during_an_edit_changes_nothing(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:edit_time")
    await chat.send("/cancel")
    assert EN["cancelled"] in chat.texts()
    assert await reload(harness, message) == message
