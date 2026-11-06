from datetime import UTC, date, datetime, time

import pytest

from conftest import FakeChat, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]


async def create(chat: FakeChat, recurrence: str, interval: str | None = None) -> None:
    await chat.send("/new")
    await chat.send("Pay rent")
    await chat.press(f"rec:{recurrence}")
    if interval is not None:
        await chat.send(interval)
    await chat.send("7.11.2026")
    await chat.send("14:45")


async def only_message(chat: FakeChat, harness: Harness):
    messages, _ = await harness.repo.list_messages(chat.user_id, 0, 10)
    assert len(messages) == 1
    return messages[0]


@pytest.mark.parametrize("recurrence", ["once", "daily", "weekly", "monthly", "yearly"])
async def test_full_flow_for_each_recurrence(
    chat: FakeChat, harness: Harness, recurrence: str
) -> None:
    await create(chat, recurrence)
    message = await only_message(chat, harness)
    assert message.text == "Pay rent"
    assert message.recurrence == Recurrence(recurrence)
    assert message.start_date == date(2026, 11, 7)
    assert message.send_time == time(14, 45)
    assert message.next_send_at == datetime(2026, 11, 7, 12, 45, tzinfo=UTC)
    assert message.status == "active"


async def test_every_n_days_asks_for_an_interval(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.send("Water the plant")
    await chat.press("rec:interval")
    assert chat.last_text == EN["prompt_interval"]
    await chat.send("10")
    await chat.send("7.11.2026")
    await chat.send("14:45")
    message = await only_message(chat, harness)
    assert message.recurrence is Recurrence.INTERVAL
    assert message.interval_days == 10


async def test_steps_ask_for_one_value_at_a_time(chat: FakeChat) -> None:
    await chat.send("/new")
    assert chat.last_text == EN["prompt_text"]
    await chat.send("Pay rent")
    assert chat.last_text == EN["prompt_recurrence"]
    assert set(chat.last_buttons()) == {
        "Only once",
        "Every day",
        "Every week",
        "Every month",
        "Every year",
        "Every N days",
        "Cancel",
    }
    await chat.press("rec:weekly")
    assert chat.last_text == EN["prompt_date"]
    await chat.send("7.11.2026")
    assert chat.last_text == EN["prompt_time"]


async def test_every_step_offers_cancel(chat: FakeChat) -> None:
    await chat.send("/new")
    assert "Cancel" in chat.last_buttons()
    await chat.send("text")
    assert "Cancel" in chat.last_buttons()
    await chat.press("rec:interval")
    assert "Cancel" in chat.last_buttons()
    await chat.send("3")
    assert "Cancel" in chat.last_buttons()
    await chat.send("7.11.2026")
    assert "Cancel" in chat.last_buttons()


async def test_confirmation_shows_details_and_kyiv_time(chat: FakeChat) -> None:
    await create(chat, "weekly")
    assert "Pay rent" in chat.last_text
    assert "Every week" in chat.last_text
    assert "14:45" in chat.last_text
    assert "Kyiv time" in chat.last_text
    assert "7.11.2026 14:45" in chat.last_text


async def test_time_prompt_mentions_kyiv_time(chat: FakeChat) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.press("rec:once")
    await chat.send("7.11.2026")
    assert "Kyiv time" in chat.last_text


@pytest.mark.parametrize(
    ("bad_value", "error"),
    [("31.02.2027", "error_date_invalid"), ("1.1.2101", "error_date_too_far")],
)
async def test_invalid_date_repeats_only_that_step(
    chat: FakeChat, harness: Harness, bad_value: str, error: str
) -> None:
    await chat.send("/new")
    await chat.send("Pay rent")
    await chat.press("rec:once")
    await chat.send(bad_value)
    assert chat.last_text == EN[error]
    await chat.send("7.11.2026")
    await chat.send("14:45")
    assert (await only_message(chat, harness)).text == "Pay rent"


@pytest.mark.parametrize("recurrence", ["once", "daily", "weekly", "monthly", "yearly"])
async def test_past_date_is_rejected_for_every_recurrence(
    chat: FakeChat, harness: Harness, recurrence: str
) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.press(f"rec:{recurrence}")
    await chat.send("5.11.2026")
    assert chat.last_text == EN["error_date_past"]
    assert await harness.repo.count_active(chat.user_id) == 0


async def test_earlier_today_is_rejected_and_later_today_accepted(
    chat: FakeChat, harness: Harness
) -> None:
    # It's 14:00 in Kyiv.
    await chat.send("/new")
    await chat.send("x")
    await chat.press("rec:daily")
    await chat.send("6.11.2026")
    await chat.send("13:59")
    assert chat.last_text == EN["error_datetime_past"]
    assert await harness.repo.count_active(chat.user_id) == 0
    await chat.send("14:01")
    assert await harness.repo.count_active(chat.user_id) == 1


async def test_invalid_time_repeats_only_that_step(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.press("rec:once")
    await chat.send("7.11.2026")
    await chat.send("25:70")
    assert chat.last_text == EN["error_time_invalid"]
    await chat.send("14:45")
    assert await harness.repo.count_active(chat.user_id) == 1


@pytest.mark.parametrize("bad_value", ["0", "1.5", "abc", "3651"])
async def test_invalid_interval_is_rejected(chat: FakeChat, bad_value: str) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.press("rec:interval")
    await chat.send(bad_value)
    assert chat.last_text == EN["error_interval_invalid"]


async def test_non_text_message_is_rejected(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.send_photo()
    assert chat.last_text == EN["error_text_empty"]
    await chat.send("Now it's text")
    assert chat.last_text == EN["prompt_recurrence"]


async def test_too_long_text_is_rejected(chat: FakeChat) -> None:
    await chat.send("/new")
    await chat.send("a" * 4097)
    assert chat.last_text == EN["error_text_too_long"]


async def test_typing_at_the_recurrence_step_asks_for_a_button(chat: FakeChat) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.send("weekly")
    assert chat.last_text == EN["error_choose_button"]


@pytest.mark.parametrize("step", [0, 1, 2, 3])
async def test_cancel_saves_nothing_at_any_step(
    chat: FakeChat, harness: Harness, step: int
) -> None:
    await chat.send("/new")
    if step >= 1:
        await chat.send("x")
    if step >= 2:
        await chat.press("rec:once")
    if step >= 3:
        await chat.send("7.11.2026")
    await chat.press("flow:cancel")
    assert EN["cancelled"] in chat.texts()
    assert await harness.repo.count_active(chat.user_id) == 0
    # The flow has really ended: plain text now gets the hint.
    await chat.send("14:45")
    assert chat.last_text == EN["unknown_input"]


async def test_cancel_command_ends_a_flow(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.send("/cancel")
    assert EN["cancelled"] in chat.texts()
    await chat.send("hello")
    assert chat.last_text == EN["unknown_input"]


async def test_another_command_ends_the_flow_without_saving(
    chat: FakeChat, harness: Harness
) -> None:
    await chat.send("/new")
    await chat.send("x")
    await chat.press("rec:once")
    await chat.send("/help")
    assert EN["help"] in chat.texts()
    await chat.send("7.11.2026")
    assert chat.last_text == EN["unknown_input"]
    assert await harness.repo.count_active(chat.user_id) == 0


async def test_unknown_slash_text_can_be_a_reminder(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.send("/water the plant")
    assert chat.last_text == EN["prompt_recurrence"]


async def test_old_recurrence_button_after_the_flow_is_stale(
    chat: FakeChat, harness: Harness
) -> None:
    await create(chat, "once")
    await chat.press("rec:daily")
    assert harness.session.calls[-1].text == EN["no_longer_available"]


async def add_active(harness: Harness, user_id: int, count: int) -> None:
    await harness.repo.get_or_create_user(user_id, "en", harness.clock.now())
    rule = Rule(Recurrence.DAILY, date(2026, 12, 1), time(9, 0))
    for _ in range(count):
        await harness.repo.create_message(user_id, "x", rule, harness.clock.now())


async def test_limit_is_enforced_when_the_flow_starts(chat: FakeChat, harness: Harness) -> None:
    await add_active(harness, chat.user_id, 100)
    await chat.send("/new")
    assert chat.last_text == EN["error_limit"]
    await chat.send("hello")
    assert chat.last_text == EN["unknown_input"]


async def test_limit_is_enforced_again_at_save(chat: FakeChat, harness: Harness) -> None:
    await add_active(harness, chat.user_id, 99)
    await chat.send("/new")
    await chat.send("x")
    await chat.press("rec:once")
    await chat.send("7.11.2026")
    # Another flow fills the last place meanwhile.
    await add_active(harness, chat.user_id, 1)
    await chat.send("14:45")
    assert chat.last_text == EN["error_limit"]
    assert await harness.repo.count_active(chat.user_id) == 100


async def test_completed_messages_do_not_count_towards_the_limit(
    chat: FakeChat, harness: Harness
) -> None:
    await add_active(harness, chat.user_id, 100)
    messages, _ = await harness.repo.list_messages(chat.user_id, 0, 1)
    await harness.repo._db.execute(
        "UPDATE scheduled_messages SET status = 'completed', next_send_at = NULL WHERE id = ?",
        (messages[0].id,),
    )
    await chat.send("/new")
    assert chat.last_text == EN["prompt_text"]


async def test_menu_button_starts_a_new_message(chat: FakeChat) -> None:
    await chat.press("menu:new")
    assert chat.last_text == EN["prompt_text"]
