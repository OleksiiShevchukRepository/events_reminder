from datetime import date, time, timedelta

from conftest import OTHER_USER, USER, FakeChat, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]


async def add(
    harness: Harness,
    recurrence: Recurrence = Recurrence.DAILY,
    user_id: int = USER,
    text: str = "x",
):
    await harness.repo.get_or_create_chat(user_id, "en", harness.clock.now())
    rule = Rule(recurrence, date(2026, 11, 7), time(14, 45))
    return await harness.repo.create_message(user_id, text, rule, harness.clock.now())


async def test_remove_asks_for_confirmation_first(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, text="Pay rent")
    await chat.press(f"msg:{message.id}:remove")
    assert "Pay rent" in chat.last_text
    assert set(chat.last_buttons()) == {"Yes, remove", "Keep"}
    assert await harness.repo.get_message(USER, message.id) is not None


async def test_confirming_deletes_the_message_and_its_delivery_records(
    chat: FakeChat, harness: Harness
) -> None:
    message = await add(harness)
    claim = await harness.repo.claim(message.id, message.next_send_at + timedelta(seconds=1))
    await harness.repo.record_sent(claim.delivery_id, message.next_send_at)
    await chat.press(f"msg:{message.id}:remove")
    await chat.press(f"msg:{message.id}:remove_yes")
    assert EN["removed"] in chat.texts()
    assert await harness.repo.get_message(USER, message.id) is None
    row = await harness.repo._db.fetch_one("SELECT COUNT(*) FROM deliveries")
    assert row[0] == 0


async def test_keep_changes_nothing(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, text="Pay rent")
    await chat.press(f"msg:{message.id}:remove")
    await chat.press(chat.last_buttons()["Keep"])
    assert await harness.repo.get_message(USER, message.id) == message
    assert "Pay rent" in chat.last_text


async def test_removed_message_is_never_claimed(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:remove")
    await chat.press(f"msg:{message.id}:remove_yes")
    later = message.next_send_at + timedelta(days=1)
    assert await harness.repo.due_messages(later, 10) == []
    assert await harness.repo.claim(message.id, later) is None


async def test_completed_message_can_be_removed(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, Recurrence.ONCE)
    claim = await harness.repo.claim(message.id, message.next_send_at + timedelta(seconds=1))
    await harness.repo.record_sent(claim.delivery_id, message.next_send_at)
    await chat.press(f"msg:{message.id}:remove")
    await chat.press(f"msg:{message.id}:remove_yes")
    assert await harness.repo.get_message(USER, message.id) is None


async def test_removing_frees_a_place_under_the_limit(chat: FakeChat, harness: Harness) -> None:
    first = await add(harness)
    for _ in range(99):
        await add(harness)
    await chat.send("/new")
    assert chat.last_text == EN["error_limit"]
    await chat.press(f"msg:{first.id}:remove")
    await chat.press(f"msg:{first.id}:remove_yes")
    await chat.send("/new")
    assert chat.last_text == EN["prompt_recurrence"]


async def test_old_button_for_a_removed_message_is_stale(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness)
    await chat.press(f"msg:{message.id}:remove")
    await chat.press(f"msg:{message.id}:remove_yes")
    for action in ("open", "remove", "remove_yes", "edit_text"):
        await chat.press(f"msg:{message.id}:{action}")
        assert harness.session.calls[-1].text == EN["no_longer_available"]


async def test_another_users_message_cannot_be_removed(chat: FakeChat, harness: Harness) -> None:
    theirs = await add(harness, user_id=OTHER_USER, text="Secret")
    await chat.press(f"msg:{theirs.id}:remove")
    assert harness.session.calls[-1].text == EN["no_longer_available"]
    await chat.press(f"msg:{theirs.id}:remove_yes")
    assert harness.session.calls[-1].text == EN["no_longer_available"]
    assert await harness.repo.get_message(OTHER_USER, theirs.id) == theirs
    assert not any("Secret" in text for text in chat.texts())


async def test_longest_text_fits_in_the_confirmation(chat: FakeChat, harness: Harness) -> None:
    message = await add(harness, text="a" * 4096)
    await chat.press(f"msg:{message.id}:remove")
    assert len(chat.last_text) <= 4096
