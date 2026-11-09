"""The bot joining, leaving and losing the right to post in groups, and supergroup
upgrades (002 FR-112, FR-115, FR-116, FR-117)."""

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.types import Chat, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated

from conftest import BOT_ID, BOT_USER, GROUP, START, FakeGroup, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES
from reminder_bot.scheduler.dispatcher import MessageDispatcher, RateLimiter

EN = LANGUAGES["en"]
UK = LANGUAGES["uk"]
ANNA = FakeGroup.member(11, "Anna")
OLENA = FakeGroup.member(33, "Olena", language="uk")
DUE = datetime(2026, 11, 7, 12, 45, tzinfo=UTC)
NEW_GROUP = -1009999


async def instant(_: float) -> None:
    pass


def scheduler(harness: Harness, tmp_path: Path) -> MessageDispatcher:
    return MessageDispatcher(
        repo=harness.repo,
        bot=Bot(f"{BOT_ID}:TEST", session=harness.session),
        clock=harness.clock,
        limiter=RateLimiter(harness.clock, instant),
        heartbeat_path=tmp_path / "heartbeat",
    )


async def add(harness: Harness, recurrence: Recurrence, text: str):
    rule = Rule(recurrence, date(2026, 11, 7), time(14, 45))
    return await harness.repo.create_message(GROUP, text, rule, harness.clock.now(), "Anna")


async def test_being_added_stores_the_group_in_the_adders_language_and_says_hello(
    harness: Harness,
) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=OLENA)
    stored = await harness.repo.get_chat(GROUP)
    assert stored.kind == "group" and stored.language == "uk"
    assert group.last_text == UK["welcome_group"]
    assert group.last_reply.message_thread_id is None


def test_the_welcome_mentions_new_replying_and_admin_rights() -> None:
    for text in (EN["welcome_group"], UK["welcome_group"]):
        assert "/new" in text
    assert "replying" in EN["welcome_group"]
    assert "admin" in EN["welcome_group"]


@pytest.mark.parametrize(
    ("new", "can_send"), [("left", True), ("kicked", True), ("restricted", False)]
)
async def test_losing_the_right_to_post_makes_the_group_unreachable(
    harness: Harness, new: str, can_send: bool
) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=ANNA)
    await group.bot_status("member", new, by=ANNA, can_send_messages=can_send)
    assert (await harness.repo.get_chat(GROUP)).unreachable_at == harness.clock.now()


async def test_being_added_back_says_hello_again(harness: Harness) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=ANNA)
    await group.bot_status("member", "left", by=ANNA)
    await group.bot_status("left", "member", by=ANNA)
    assert group.texts() == [EN["welcome_group"], EN["welcome_group"]]
    assert (await harness.repo.get_chat(GROUP)).unreachable_at is None


async def test_rights_changes_alone_post_no_welcome(harness: Harness) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=ANNA)
    await group.bot_status("member", "administrator", by=ANNA)
    await group.bot_status("administrator", "restricted", by=ANNA, can_send_messages=False)
    assert (await harness.repo.get_chat(GROUP)).unreachable_at is not None
    await group.bot_status("restricted", "member", by=ANNA)
    assert (await harness.repo.get_chat(GROUP)).unreachable_at is None
    assert group.texts() == [EN["welcome_group"]]


async def test_a_restricted_bot_that_may_still_post_stays_reachable(harness: Harness) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=ANNA)
    await group.bot_status("member", "restricted", by=ANNA, can_send_messages=True)
    assert (await harness.repo.get_chat(GROUP)).unreachable_at is None


async def test_nothing_is_sent_while_out_and_return_has_no_catch_up(
    harness: Harness, tmp_path: Path
) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=ANNA)
    daily = await add(harness, Recurrence.DAILY, "Daily")
    once = await add(harness, Recurrence.ONCE, "Once")
    await group.bot_status("member", "left", by=ANNA)
    harness.session.calls.clear()

    harness.clock.set(DUE + timedelta(days=3, hours=1))
    sender = scheduler(harness, tmp_path)
    await sender.run_once()
    assert harness.session.sent(GROUP) == []

    await group.bot_status("left", "member", by=ANNA)
    await sender.run_once()
    texts = harness.session.sent_texts(GROUP)
    # The welcome, then the overdue one-time reminder with its note. No daily catch-up.
    assert texts[0] == EN["welcome_group"]
    assert "was due" in texts[1]
    assert texts[2:] == ["Once"]
    stored = await harness.repo.get_message(GROUP, daily.id)
    assert stored.next_send_at == DUE + timedelta(days=4)
    assert (await harness.repo.get_message(GROUP, once.id)).status == "completed"


async def test_channel_membership_changes_store_nothing(harness: Harness) -> None:
    channel = Chat(id=-100777, type="channel", title="News")
    await harness.feed(
        my_chat_member=ChatMemberUpdated(
            chat=channel,
            from_user=ANNA,
            date=START,
            old_chat_member=ChatMemberLeft(user=BOT_USER),
            new_chat_member=ChatMemberMember(user=BOT_USER),
        )
    )
    assert await harness.repo.get_chat(-100777) is None
    assert harness.session.sent() == []


# Supergroup upgrade


async def test_upgrade_message_moves_everything_once(harness: Harness, tmp_path: Path) -> None:
    group = harness.group()
    await group.bot_status("left", "member", by=OLENA)
    reminder = await add(harness, Recurrence.DAILY, "Bins out")
    await group.migrate(NEW_GROUP, by=ANNA)
    await group.migrate(NEW_GROUP, by=ANNA)
    assert await harness.repo.get_chat(GROUP) is None
    moved = await harness.repo.get_chat(NEW_GROUP)
    assert moved.kind == "group" and moved.language == "uk"
    assert (await harness.repo.get_message(NEW_GROUP, reminder.id)).text == "Bins out"

    harness.session.calls.clear()
    harness.clock.set(DUE)
    await scheduler(harness, tmp_path).run_once()
    assert harness.session.sent_texts(NEW_GROUP) == ["Bins out"]
    assert harness.session.sent(GROUP) == []
