"""Listing, changing and removing a group's reminders, and the group's language
(002 US2, US3, US4)."""

from datetime import date, time

from conftest import GROUP, OTHER_GROUP, USER, FakeGroup, Harness
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import LANGUAGES

EN = LANGUAGES["en"]
UK = LANGUAGES["uk"]
ANNA = FakeGroup.member(11, "Anna")
BORYS = FakeGroup.member(22, "Borys", "Shevchenko")
OLENA = FakeGroup.member(33, "Olena", language="uk")
RULE = Rule(Recurrence.DAILY, date(2026, 12, 1), time(9, 0))


async def add(harness: Harness, text: str, chat_id: int = GROUP, by: str | None = "Anna"):
    kind = "group" if chat_id < 0 else "private"
    await harness.repo.get_or_create_chat(chat_id, "en", harness.clock.now(), kind=kind)
    return await harness.repo.create_message(
        chat_id, text, RULE, harness.clock.now(), by if chat_id < 0 else None
    )


# US2: the group's list


async def test_group_list_shows_only_the_groups_reminders(harness: Harness) -> None:
    await add(harness, "Group one")
    await add(harness, "Other group", chat_id=OTHER_GROUP)
    await add(harness, "Anna's private", chat_id=ANNA.id)
    group = harness.group()
    await group.send("/list", ANNA)
    assert "Group one" in group.last_text
    assert "Other group" not in group.last_text
    assert "Anna's private" not in group.last_text

    await harness.chat(user_id=ANNA.id).send("/list")
    private = harness.session.sent_texts(ANNA.id)[-1]
    assert "Anna's private" in private and "Group one" not in private


async def test_group_list_pages_by_ten(harness: Harness) -> None:
    for index in range(12):
        await add(harness, f"R{index:02d}")
    group = harness.group()
    await group.send("/list", ANNA)
    assert "page 1 of 2" in group.last_text
    await group.press(group.last_buttons()["Next"], BORYS)
    assert "page 2 of 2" in group.last_text


async def test_a_button_cant_reach_another_chats_reminder(harness: Harness) -> None:
    theirs = await add(harness, "Secret", chat_id=OTHER_GROUP)
    group = harness.group()
    await group.send("/list", ANNA)
    for action in ("open", "edit_text", "remove", "remove_yes"):
        await group.press(f"msg:{theirs.id}:{action}", ANNA)
        assert harness.session.callback_answers()[-1] == EN["no_longer_available"]
    assert all("Secret" not in text for text in group.texts())
    assert await harness.repo.get_message(OTHER_GROUP, theirs.id) is not None


async def test_people_who_left_cant_use_the_groups_buttons(harness: Harness) -> None:
    reminder = await add(harness, "Bins out")
    harness.session.member_status[BORYS.id] = "left"
    group = harness.group()
    for data in (f"msg:{reminder.id}:open", f"msg:{reminder.id}:remove_yes", "page:0"):
        await group.press(data, BORYS)
        assert harness.session.callback_answers()[-1] == EN["no_longer_available"]
    assert group.replies() == []
    assert await harness.repo.get_message(GROUP, reminder.id) is not None


async def test_empty_group_list_offers_a_new_reminder(harness: Harness) -> None:
    group = harness.group()
    await group.send("/list", ANNA)
    assert group.last_text == EN["list_empty"]
    assert "New reminder" in group.last_buttons()


async def test_group_screen_shows_who_created_it(harness: Harness) -> None:
    reminder = await add(harness, "Bins out", by="Anna Koval")
    group = harness.group()
    await group.press(f"msg:{reminder.id}:open", BORYS)
    assert "Created by: Anna Koval" in group.last_text
    assert "Last changed by" not in group.last_text


async def test_private_screens_show_no_names(harness: Harness) -> None:
    reminder = await add(harness, "Pay rent", chat_id=USER)
    chat = harness.chat()
    await chat.press(f"msg:{reminder.id}:open")
    assert "Created by" not in chat.last_text


# US3: any member changes or removes


async def test_another_member_can_change_a_reminder_and_is_named(harness: Harness) -> None:
    reminder = await add(harness, "Bins out", by="Anna")
    group = harness.group()
    await group.press(f"msg:{reminder.id}:edit_time", BORYS)
    assert group.last_text.startswith("Borys Shevchenko, send the new time")
    await group.answer("20:30", BORYS)
    assert group.last_text.startswith("Updated by Borys Shevchenko.")
    stored = await harness.repo.get_message(GROUP, reminder.id)
    assert stored.send_time == time(20, 30)
    assert stored.created_by_name == "Anna"
    assert stored.changed_by_name == "Borys Shevchenko"

    await group.press(f"msg:{reminder.id}:open", ANNA)
    assert "Created by: Anna" in group.last_text
    assert "Last changed by: Borys Shevchenko" in group.last_text


async def test_text_and_recurrence_edits_record_the_member(harness: Harness) -> None:
    reminder = await add(harness, "Bins out")
    group = harness.group()
    await group.press(f"msg:{reminder.id}:edit_text", BORYS)
    await group.answer("Bins out tonight", BORYS)
    await group.press(f"msg:{reminder.id}:edit_rec", ANNA)
    await group.press("rec:weekly", ANNA)
    stored = await harness.repo.get_message(GROUP, reminder.id)
    assert stored.text == "Bins out tonight"
    assert stored.recurrence is Recurrence.WEEKLY
    assert stored.changed_by_name == "Anna"


async def test_edit_flows_accept_only_the_member_who_started_them(harness: Harness) -> None:
    reminder = await add(harness, "Bins out")
    group = harness.group()
    await group.press(f"msg:{reminder.id}:edit_text", ANNA)
    await group.answer("Borys was here", BORYS)
    assert (await harness.repo.get_message(GROUP, reminder.id)).text == "Bins out"
    await group.answer("Anna's text", ANNA)
    assert (await harness.repo.get_message(GROUP, reminder.id)).text == "Anna's text"
    assert len(harness.session.deleted(GROUP)) == 2


async def test_another_member_can_remove_a_reminder_and_is_named(harness: Harness) -> None:
    reminder = await add(harness, "Bins out", by="Anna")
    group = harness.group()
    await group.press(f"msg:{reminder.id}:remove", BORYS)
    await group.press(f"msg:{reminder.id}:remove_yes", BORYS)
    assert group.last_text == "Removed by Borys Shevchenko:\n\nBins out"
    assert await harness.repo.get_message(GROUP, reminder.id) is None


async def test_private_removal_keeps_its_wording(harness: Harness) -> None:
    reminder = await add(harness, "Pay rent", chat_id=USER)
    chat = harness.chat()
    await chat.press(f"msg:{reminder.id}:remove_yes")
    assert chat.last_text == EN["removed"]


async def test_anonymous_admins_cant_use_edit_or_remove_buttons(harness: Harness) -> None:
    reminder = await add(harness, "Bins out")
    harness.session.member_status[ANNA.id] = "anonymous"
    group = harness.group()
    for action in ("edit_text", "remove", "remove_yes"):
        await group.press(f"msg:{reminder.id}:{action}", ANNA)
        assert harness.session.callback_answers()[-1] == EN["anonymous_admin"]
    await group.press(f"msg:{reminder.id}:open", ANNA)
    assert "Bins out" in group.last_text
    assert await harness.repo.get_message(GROUP, reminder.id) is not None


# US4: one language per group


async def test_group_language_comes_from_the_first_member_to_use_it(harness: Harness) -> None:
    group = harness.group()
    await group.send("/help", OLENA)
    assert group.last_text == UK["help_group"]
    await group.send("/help", ANNA)
    assert group.last_text == UK["help_group"]


async def test_any_member_changes_the_groups_language_for_everyone(harness: Harness) -> None:
    group = harness.group()
    await group.send("/help", ANNA)
    await group.send("/language", BORYS)
    await group.press("lang:uk", BORYS)
    assert group.last_text == UK["language_changed"]
    await group.send("/help", ANNA)
    assert group.last_text == UK["help_group"]
    assert (await harness.repo.get_chat(GROUP)).language == "uk"


async def test_group_and_private_languages_are_independent(harness: Harness) -> None:
    group = harness.group()
    await group.send("/help", ANNA)
    private = harness.chat(user_id=ANNA.id)
    await private.send("/language")
    await private.press("lang:uk")
    await group.send("/help", ANNA)
    assert group.last_text == EN["help_group"]
    await group.send("/language", ANNA)
    await group.press("lang:uk", ANNA)
    assert (await harness.repo.get_chat(ANNA.id)).language == "uk"
    await group.press("lang:en", ANNA)
    assert (await harness.repo.get_chat(ANNA.id)).language == "uk"
