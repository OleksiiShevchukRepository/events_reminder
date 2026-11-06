from datetime import UTC, date, datetime, time, timedelta

from conftest import OTHER_USER, USER, FakeChat, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]


async def add(
    harness: Harness,
    text: str,
    recurrence: Recurrence = Recurrence.DAILY,
    start: date = date(2026, 12, 1),
    user_id: int = USER,
    interval_days: int | None = None,
):
    await harness.repo.get_or_create_user(user_id, "en", harness.clock.now())
    rule = Rule(recurrence, start, time(14, 45), interval_days)
    return await harness.repo.create_message(user_id, text, rule, harness.clock.now())


async def complete(harness: Harness, message, *, failed: bool = False) -> None:
    now = message.next_send_at
    claim = await harness.repo.claim(message.id, now + timedelta(seconds=1))
    if failed:
        await harness.repo.record_failed(claim.delivery_id, now, "TelegramBadRequest")
    else:
        await harness.repo.record_sent(claim.delivery_id, now)


async def test_empty_list_says_so_and_offers_new_message(chat: FakeChat) -> None:
    await chat.send("/list")
    assert chat.last_text == EN["list_empty"]
    assert chat.last_buttons() == {"New message": "menu:new"}


async def test_entry_shows_preview_recurrence_time_next_send_and_status(
    chat: FakeChat, harness: Harness
) -> None:
    await add(harness, "Water the plant", Recurrence.INTERVAL, date(2026, 11, 7), interval_days=10)
    await chat.send("/list")
    text = chat.last_text
    assert "Water the plant" in text
    assert "Every 10 days" in text
    assert "14:45" in text
    assert "7.11.2026 14:45" in text
    assert "Active" in text


async def test_long_text_is_shortened_to_a_preview(chat: FakeChat, harness: Harness) -> None:
    await add(harness, "a" * 500)
    await chat.send("/list")
    assert "a" * 500 not in chat.last_text
    assert "…" in chat.last_text


async def test_active_messages_come_first_by_next_send_then_completed(
    chat: FakeChat, harness: Harness
) -> None:
    done = await add(harness, "Done", Recurrence.ONCE, date(2026, 11, 7))
    await complete(harness, done)
    await add(harness, "Later", start=date(2027, 1, 1))
    await add(harness, "Sooner", start=date(2026, 12, 1))
    await chat.send("/list")
    text = chat.last_text
    assert text.index("Sooner") < text.index("Later") < text.index("Done")
    assert "Completed" in text


async def test_paging_at_five_reaches_every_message(chat: FakeChat, harness: Harness) -> None:
    for number in range(12):
        await add(harness, f"Msg{number:02d}", start=date(2026, 12, 1) + timedelta(days=number))
    await chat.send("/list")
    assert "page 1 of 3" in chat.last_text
    buttons = chat.last_buttons()
    assert len([label for label in buttons if label.startswith(tuple("12345"))]) == 5
    assert "Previous" not in buttons
    seen = set()
    for _ in range(3):
        seen |= {f"Msg{n:02d}" for n in range(12) if f"Msg{n:02d}" in chat.last_text}
        buttons = chat.last_buttons()
        if "Next" in buttons:
            await chat.press(buttons["Next"])
    assert seen == {f"Msg{n:02d}" for n in range(12)}
    assert "page 3 of 3" in chat.last_text
    assert "Next" not in chat.last_buttons()
    assert "Previous" in chat.last_buttons()


async def test_numbers_continue_across_pages(chat: FakeChat, harness: Harness) -> None:
    for number in range(6):
        await add(harness, f"Msg{number}", start=date(2026, 12, 1) + timedelta(days=number))
    await chat.send("/list")
    await chat.press("page:1")
    assert "6. Msg5" in chat.last_text


async def test_page_beyond_the_end_shows_the_last_page(chat: FakeChat, harness: Harness) -> None:
    await add(harness, "Only one")
    await chat.send("/list")
    await chat.press("page:7")
    assert "Only one" in chat.last_text


async def test_message_screen_shows_the_full_text(chat: FakeChat, harness: Harness) -> None:
    text = "a" * 300
    message = await add(harness, text)
    await chat.send("/list")
    await chat.press(f"msg:{message.id}:open")
    assert text in chat.last_text
    assert "Kyiv time" in chat.last_text
    assert "Every day" in chat.last_text


async def test_longest_text_is_shown_in_full_with_details_after_it(
    chat: FakeChat, harness: Harness
) -> None:
    text = "a" * 4096
    message = await add(harness, text)
    await chat.press(f"msg:{message.id}:open")
    assert text in chat.texts()
    assert all(len(sent) <= 4096 for sent in chat.texts())
    assert "Kyiv time" in chat.last_text
    assert "Edit text" in chat.last_buttons()


async def test_active_screen_buttons(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, "x")
    await chat.press(f"msg:{message.id}:open")
    assert set(chat.last_buttons()) == {
        "Edit text",
        "Edit recurrence",
        "Edit date",
        "Edit time",
        "Remove",
        "Back",
    }


async def test_active_interval_screen_buttons(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, "x", Recurrence.INTERVAL, interval_days=3)
    await chat.press(f"msg:{message.id}:open")
    assert set(chat.last_buttons()) == {
        "Edit text",
        "Edit recurrence",
        "Edit date and interval",
        "Edit time",
        "Remove",
        "Back",
    }


async def test_completed_screen_only_offers_remove_and_back(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, "x", Recurrence.ONCE, date(2026, 11, 7))
    await complete(harness, message)
    await chat.press(f"msg:{message.id}:open")
    assert set(chat.last_buttons()) == {"Remove", "Back"}


async def test_failed_one_time_message_shows_as_not_delivered(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness, "x", Recurrence.ONCE, date(2026, 11, 7))
    await complete(harness, message, failed=True)
    await chat.send("/list")
    assert "Not delivered" in chat.last_text
    await chat.press(f"msg:{message.id}:open")
    assert "Not delivered" in chat.last_text


async def test_one_time_message_being_sent_shows_sending(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, "x", Recurrence.ONCE, date(2026, 11, 7))
    harness.clock.set(datetime(2026, 11, 7, 12, 45, tzinfo=UTC))
    await harness.repo.claim(message.id, harness.clock.now())
    await chat.send("/list")
    assert "Sending" in chat.last_text


async def test_users_only_see_their_own_messages(chat: FakeChat, harness: Harness) -> None:
    await add(harness, "Mine")
    await add(harness, "Theirs", user_id=OTHER_USER)
    await chat.send("/list")
    assert "Mine" in chat.last_text
    assert "Theirs" not in chat.last_text
    other = harness.chat(user_id=OTHER_USER)
    await other.send("/list")
    assert "Theirs" in other.last_text
    assert "Mine" not in other.last_text


async def test_another_users_message_gets_the_same_answer_as_a_removed_one(
    chat: FakeChat, harness: Harness
) -> None:
    theirs = await add(harness, "Theirs", user_id=OTHER_USER)
    await chat.press(f"msg:{theirs.id}:open")
    first = harness.session.calls[-1].text
    await chat.press("msg:999999:open")
    second = harness.session.calls[-1].text
    assert first == second == EN["no_longer_available"]
    assert not any("Theirs" in text for text in chat.texts())


async def test_list_ends_a_flow(chat: FakeChat) -> None:
    await chat.send("/new")
    await chat.send("/list")
    await chat.send("hello")
    assert chat.last_text == EN["unknown_input"]


async def test_menu_button_and_back_show_the_list(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, "Mine")
    await chat.press("menu:list")
    assert "Mine" in chat.last_text
    await chat.press(f"msg:{message.id}:open")
    await chat.press("page:0")
    assert "page 1 of 1" in chat.last_text
