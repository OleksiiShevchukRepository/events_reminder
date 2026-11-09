"""Flows delete their questions and answers when they end (002 FR-119, FR-120, SC-107)."""

from datetime import date, time

from conftest import GROUP, FakeChat, FakeGroup, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]
ANNA = FakeGroup.member(11, "Anna")


async def test_saving_a_group_reminder_leaves_only_the_confirmation(harness: Harness) -> None:
    group = harness.group()
    member_ids = [await group.send("/new", ANNA)]
    await group.press("rec:once", ANNA)
    member_ids.append(await group.answer("Bins out", ANNA))
    member_ids.append(await group.answer("31.02.2027", ANNA))  # An error reply follows.
    member_ids.append(await group.answer("7.11.2026", ANNA))
    member_ids.append(await group.answer("19:00", ANNA))

    session = harness.session
    deletions = session.deleted(GROUP)
    assert len(deletions) == 2
    bot_deleted, member_deleted = (set(call.message_ids) for call in deletions)
    assert member_deleted == set(member_ids)
    # Recurrence, text, date, the error, and time questions: everything but the confirmation.
    assert len(bot_deleted) == 5
    confirmation_id = max(session.bot_message_ids)
    assert confirmation_id not in bot_deleted
    assert group.last_text.startswith("Saved by Anna.")


async def test_without_delete_rights_the_bots_questions_still_go(harness: Harness) -> None:
    harness.session.can_delete_members_messages = False
    group = harness.group()
    await group.send("/new", ANNA)
    await group.press("rec:once", ANNA)
    await group.answer("Bins out", ANNA)
    await group.answer("7.11.2026", ANNA)
    await group.answer("19:00", ANNA)
    bot_call, member_call = harness.session.deleted(GROUP)
    assert set(bot_call.message_ids) <= harness.session.bot_message_ids
    assert not set(member_call.message_ids) & harness.session.bot_message_ids
    # The member deletion failed, and the reminder was still saved.
    _, total = await harness.repo.list_messages(GROUP, 0, 10)
    assert total == 1
    assert group.last_text.startswith("Saved by Anna.")


async def test_cancel_button_and_other_commands_clean_up_too(harness: Harness) -> None:
    group = harness.group()
    first_new = await group.send("/new", ANNA)
    await group.press("rec:once", ANNA)
    questions = set(harness.session.bot_message_ids)
    await group.press("flow:cancel", ANNA)
    assert {first_new} | questions <= harness.session.deleted_ids(GROUP)
    assert group.last_text == EN["cancelled"]

    second_new = await group.send("/new", ANNA)
    await group.send("/help", ANNA)
    assert second_new in harness.session.deleted_ids(GROUP)
    assert group.last_text == EN["help_group"]


async def test_private_flows_delete_both_sides(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.press("rec:once")
    await chat.send("Pay rent")
    await chat.send("7.11.2026")
    await chat.send("14:45")
    bot_call, member_call = harness.session.deleted(chat.user_id)
    assert len(bot_call.message_ids) == 4
    assert len(member_call.message_ids) == 4  # /new and three answers.
    assert chat.last_text.startswith("Saved.")


async def test_private_cancel_leaves_only_cancelled(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/new")
    await chat.press("flow:cancel")
    [bot_call, member_call] = harness.session.deleted(chat.user_id)
    assert len(bot_call.message_ids) == 1
    assert len(member_call.message_ids) == 1
    assert chat.last_text == EN["cancelled"]


async def test_update_flows_clean_up_the_same_way(chat: FakeChat, harness: Harness) -> None:
    repo, now = harness.repo, harness.clock.now()
    await repo.get_or_create_chat(chat.user_id, "en", now)
    message = await repo.create_message(
        chat.user_id, "Pay rent", Rule(Recurrence.DAILY, date(2026, 12, 1), time(9, 0)), now
    )
    await chat.press(f"msg:{message.id}:edit_time")
    await chat.send("25:00")
    await chat.send("10:00")
    bot_call, member_call = harness.session.deleted(chat.user_id)
    assert len(bot_call.message_ids) == 2  # The question and the error.
    assert len(member_call.message_ids) == 2
    assert chat.last_text.startswith("Updated.")
