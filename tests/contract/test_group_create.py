"""Creating reminders in a group (002 US1)."""

from datetime import date, time

import pytest
from aiogram.types import ForceReply

from conftest import GROUP, USER, FakeGroup, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]
ANNA = FakeGroup.member(11, "Anna", "Koval")
BORYS = FakeGroup.member(22, "Borys")


async def create(
    group: FakeGroup, member, recurrence: str = "once", text: str = "Bins out"
) -> None:
    await group.send("/new", member)
    await group.press(f"rec:{recurrence}", member)
    await group.answer(text, member)
    if recurrence == "interval":
        await group.answer("3", member)
    await group.answer("7.11.2026", member)
    await group.answer("19:00", member)


async def group_reminders(harness: Harness, chat_id: int = GROUP):
    messages, _ = await harness.repo.list_messages(chat_id, 0, 100)
    return messages


@pytest.mark.parametrize("recurrence", ["once", "daily", "weekly", "monthly", "yearly", "interval"])
async def test_full_flow_saves_a_group_reminder_with_its_creator(
    harness: Harness, recurrence: str
) -> None:
    group = harness.group()
    await create(group, ANNA, recurrence)
    [reminder] = await group_reminders(harness)
    assert reminder.chat_id == GROUP
    assert reminder.recurrence is Recurrence(recurrence)
    assert reminder.text == "Bins out"
    assert reminder.created_by_name == "Anna Koval"
    assert reminder.changed_by_name is None


async def test_the_confirmation_names_the_member(harness: Harness) -> None:
    group = harness.group()
    await create(group, ANNA)
    assert group.last_text.startswith("Saved by Anna Koval.")
    assert "Bins out" in group.last_text


async def test_text_questions_mention_the_member_and_open_the_reply_box(
    harness: Harness,
) -> None:
    group = harness.group()
    await group.send("/new", ANNA)
    await group.press("rec:once", ANNA)
    question = group.last_reply
    assert question.text.startswith("Anna Koval, send the text")
    assert EN["cancel_hint"] in question.text
    assert isinstance(question.reply_markup, ForceReply)
    assert question.reply_markup.selective is True
    [mention] = question.entities
    assert mention.type == "text_mention"
    assert mention.user.id == ANNA.id
    assert mention.offset == 0 and mention.length == len("Anna Koval")


async def test_the_recurrence_question_keeps_its_buttons_and_cancel(harness: Harness) -> None:
    group = harness.group()
    await group.send("/new", ANNA)
    assert group.last_text.startswith("Anna Koval, how often")
    assert "Cancel" in group.last_buttons()
    assert "Every week" in group.last_buttons()


async def test_another_members_messages_and_buttons_change_nothing(harness: Harness) -> None:
    group = harness.group()
    await group.send("/new", ANNA)
    await group.press("rec:weekly", BORYS)
    assert harness.session.callback_answers()[-1] == EN["not_your_request"]
    await group.press("flow:cancel", BORYS)
    assert harness.session.callback_answers()[-1] == EN["not_your_request"]
    await group.press("rec:once", ANNA)
    sent_before = len(group.replies())
    await group.answer("Borys's text", BORYS)
    assert len(group.replies()) == sent_before  # Ignored without a reply.
    await group.answer("Bins out", ANNA)
    await group.answer("7.11.2026", ANNA)
    await group.answer("19:00", ANNA)
    [reminder] = await group_reminders(harness)
    assert reminder.text == "Bins out"
    assert reminder.recurrence is Recurrence.ONCE


async def test_two_members_flows_never_mix(harness: Harness) -> None:
    group = harness.group()
    await group.send("/new", ANNA)
    await group.send("/new", BORYS)
    await group.press("rec:daily", ANNA)
    await group.press("rec:weekly", BORYS)
    await group.answer("Anna's reminder", ANNA)
    await group.answer("Borys's reminder", BORYS)
    for member in (ANNA, BORYS):
        await group.answer("7.11.2026", member)
    await group.answer("19:00", BORYS)
    await group.answer("20:00", ANNA)
    reminders = {r.text: r for r in await group_reminders(harness)}
    assert reminders["Anna's reminder"].recurrence is Recurrence.DAILY
    assert reminders["Anna's reminder"].send_time == time(20, 0)
    assert reminders["Anna's reminder"].created_by_name == "Anna Koval"
    assert reminders["Borys's reminder"].recurrence is Recurrence.WEEKLY
    assert reminders["Borys's reminder"].send_time == time(19, 0)
    assert reminders["Borys's reminder"].created_by_name == "Borys"


async def test_invalid_answers_repeat_only_that_step(harness: Harness) -> None:
    group = harness.group()
    await group.send("/new", ANNA)
    await group.press("rec:once", ANNA)
    await group.answer("Bins out", ANNA)
    await group.answer("31.02.2027", ANNA)
    assert group.last_text.startswith("Anna Koval, that isn't a valid date")
    await group.answer("7.11.2026", ANNA)
    await group.answer("19:00", ANNA)
    assert len(await group_reminders(harness)) == 1


async def test_cancel_saves_nothing(harness: Harness) -> None:
    group = harness.group()
    await group.send("/new", ANNA)
    await group.press("rec:once", ANNA)
    await group.answer("Bins out", ANNA)
    await group.send("/cancel", ANNA)
    assert group.last_text == EN["cancelled"]
    assert await group_reminders(harness) == []


async def test_the_group_limit_is_separate_from_members_private_limits(harness: Harness) -> None:
    repo, now = harness.repo, harness.clock.now()
    rule = Rule(Recurrence.DAILY, date(2026, 12, 1), time(9, 0))
    await repo.get_or_create_chat(GROUP, "en", now, kind="group")
    for _ in range(100):
        await repo.create_message(GROUP, "x", rule, now)
    await repo.get_or_create_chat(ANNA.id, "en", now)
    group = harness.group()
    await group.send("/new", ANNA)
    assert group.last_text == EN["error_limit"]
    # Anna's own private chat is unaffected.
    await harness.chat(user_id=ANNA.id).send("/new")
    assert harness.session.sent_texts(ANNA.id)[-1] == EN["prompt_recurrence"]
    assert await repo.count_active(ANNA.id) == 0


async def test_questions_and_confirmation_stay_in_the_members_topic(harness: Harness) -> None:
    group = harness.group(forum=True)
    await group.send("/new", ANNA, thread_id=42)
    await group.press("rec:once", ANNA, thread_id=42)
    await group.answer("Bins out", ANNA, thread_id=42)
    await group.answer("7.11.2026", ANNA, thread_id=42)
    await group.answer("19:00", ANNA, thread_id=42)
    assert {reply.message_thread_id for reply in group.replies()} == {42}


async def test_an_anonymous_admin_is_asked_to_turn_off_anonymity(harness: Harness) -> None:
    group = harness.group()
    await group.send("/new", ANNA, anonymous=True)
    assert group.last_text == EN["anonymous_admin"]
    assert await harness.repo.list_messages(GROUP, 0, 10) == ([], 0)
    await group.send("/list", ANNA, anonymous=True)
    assert group.last_text == EN["list_empty"]


async def test_a_group_reminder_never_reaches_a_private_chat(harness: Harness) -> None:
    group = harness.group()
    await create(group, ANNA)
    assert harness.session.sent(ANNA.id) == []
    assert harness.session.sent(USER) == []
