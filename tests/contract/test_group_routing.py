"""What the bot reacts to in groups, and what it ignores (002 FR-113, FR-117, research §5)."""

from aiogram.types import Chat, Message

from conftest import BOT_USERNAME, GROUP, START, FakeGroup, Harness
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]
ANNA = FakeGroup.member(11, "Anna", "Koval")


async def test_ordinary_group_chat_gets_no_reply_and_stores_nothing(harness: Harness) -> None:
    group = harness.group()
    await group.send("Who's buying milk?", ANNA)
    await group.send("/weather", ANNA)
    await group.send("/help@some_other_bot", ANNA)
    assert group.replies() == []
    assert await harness.repo.get_chat(GROUP) is None


async def test_a_command_creates_the_group_and_replies_in_the_same_topic(
    harness: Harness,
) -> None:
    group = harness.group(forum=True)
    await group.send("/help", ANNA, thread_id=77)
    stored = await harness.repo.get_chat(GROUP)
    assert stored is not None and stored.kind == "group"
    assert group.last_text == EN["help_group"]
    assert group.last_reply.message_thread_id == 77


async def test_a_command_addressed_to_this_bot_by_name_works(harness: Harness) -> None:
    group = harness.group()
    await group.send(f"/help@{BOT_USERNAME}", ANNA)
    assert group.last_text == EN["help_group"]


async def test_channel_posts_store_nothing(harness: Harness) -> None:
    await harness.feed(
        channel_post=Message(
            message_id=harness.next_id(),
            date=START,
            chat=Chat(id=-100999, type="channel", title="News"),
            text="/new",
        )
    )
    assert await harness.repo.get_chat(-100999) is None
    assert harness.session.sent() == []


async def test_private_chats_still_get_the_hint_for_plain_text(harness: Harness) -> None:
    chat = harness.chat()
    await chat.send("hello")
    assert chat.last_text == EN["unknown_input"]
