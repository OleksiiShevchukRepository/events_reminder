"""A private chat keeps only the bot's current screen, plus delivered reminders (002 FR-124)."""

from datetime import UTC, date, datetime, time
from pathlib import Path

from aiogram import Bot

from conftest import BOT_ID, FakeChat, FakeGroup, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter

EN = LANGUAGES["en"]
DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)


def last_sent_id(harness: Harness) -> int:
    return max(harness.session.bot_message_ids)


async def screen(harness: Harness, chat: FakeChat) -> list[int]:
    """The current screen, as stored in the database, so it survives restarts."""
    return await harness.repo.get_screen(chat.user_id)


async def test_a_new_screen_deletes_the_old_one_and_the_typed_commands(
    chat: FakeChat, harness: Harness
) -> None:
    start = await chat.send("/start")
    welcome = last_sent_id(harness)
    assert await screen(harness, chat) == [welcome]

    list_command = await chat.send("/list")
    listing = last_sent_id(harness)
    assert await screen(harness, chat) == [listing]
    deleted = harness.session.deleted_ids(chat.user_id)
    assert {start, welcome, list_command} <= deleted
    assert listing not in deleted


async def test_stray_text_and_its_hint_are_cleared_by_the_next_screen(
    chat: FakeChat, harness: Harness
) -> None:
    hello = await chat.send("hello")
    hint = last_sent_id(harness)
    assert chat.last_text == EN["unknown_input"]
    assert hello in harness.session.deleted_ids(chat.user_id)
    await chat.send("/help")
    assert hint in harness.session.deleted_ids(chat.user_id)


async def test_buttons_on_the_current_screen_edit_it_and_delete_nothing(
    chat: FakeChat, harness: Harness
) -> None:
    await chat.send("/list")
    listing = last_sent_id(harness)
    before = harness.session.deleted_ids(chat.user_id)
    await chat.press("page:0", on_message=listing)
    assert harness.session.deleted_ids(chat.user_id) == before
    assert await screen(harness, chat) == [listing]


async def test_a_button_on_an_older_message_clears_the_current_screen(
    chat: FakeChat, harness: Harness
) -> None:
    await chat.send("/list")
    old_list = last_sent_id(harness)
    await chat.send("/help")
    help_screen = last_sent_id(harness)
    await chat.press("page:0", on_message=old_list)
    assert help_screen in harness.session.deleted_ids(chat.user_id)
    assert await screen(harness, chat) == [old_list]


async def test_a_saved_reminder_replaces_the_menu_it_started_from(
    chat: FakeChat, harness: Harness
) -> None:
    await chat.send("/start")
    welcome = last_sent_id(harness)
    await chat.send("/new")
    await chat.press("rec:once")
    await chat.send("Pay rent")
    await chat.send("7.11.2026")
    await chat.send("14:45")
    confirmation = last_sent_id(harness)
    assert welcome in harness.session.deleted_ids(chat.user_id)
    assert await screen(harness, chat) == [confirmation]
    assert chat.last_text.startswith("Saved.")


async def test_cancel_leaves_only_cancelled(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/start")
    await chat.send("/new")
    await chat.send("/cancel")
    cancelled = last_sent_id(harness)
    assert chat.last_text == EN["cancelled"]
    assert await screen(harness, chat) == [cancelled]


async def test_a_long_reminder_screen_is_cleared_as_a_whole(
    chat: FakeChat, harness: Harness
) -> None:
    repo, now = harness.repo, harness.clock.now()
    await repo.get_or_create_chat(chat.user_id, "en", now)
    rule = Rule(Recurrence.DAILY, date(2026, 12, 1), time(9, 0))
    message = await repo.create_message(chat.user_id, "a" * 4096, rule, now)
    await chat.press(f"msg:{message.id}:open")
    two_parts = await screen(harness, chat)
    assert len(two_parts) == 2
    await chat.send("/help")
    assert set(two_parts) <= harness.session.deleted_ids(chat.user_id)


async def test_delivered_reminders_are_never_deleted(
    chat: FakeChat, harness: Harness, tmp_path: Path
) -> None:
    repo, now = harness.repo, harness.clock.now()
    await repo.get_or_create_chat(chat.user_id, "en", now)
    rule = Rule(Recurrence.ONCE, date(2026, 11, 7), time(14, 45))
    await repo.create_message(chat.user_id, "Pay rent", rule, now)

    async def instant(_: float) -> None:
        pass

    await chat.send("/start")
    harness.clock.set(DUE)
    await MessageDispatcher(
        repo=repo,
        bot=Bot(f"{BOT_ID}:TEST", session=harness.session),
        clock=harness.clock,
        limiter=RateLimiter(harness.clock, instant),
        heartbeat_path=tmp_path / "heartbeat",
    ).run_once()
    reminder = last_sent_id(harness)
    await chat.send("/list")
    await chat.send("/help")
    assert reminder not in harness.session.deleted_ids(chat.user_id)


async def test_groups_keep_their_screens(harness: Harness) -> None:
    group = harness.group()
    anna = FakeGroup.member(11, "Anna")
    await group.send("/help", anna)
    await group.send("/list", anna)
    await group.send("/help", anna)
    assert harness.session.deleted(group.chat_id) == []
