from conftest import FakeChat, Harness
from reminder_bot.i18n import LANGUAGES


async def test_start_registers_a_new_user_and_explains_the_actions(
    chat: FakeChat, harness: Harness
) -> None:
    await chat.send("/start")
    assert await harness.repo.get_chat(chat.user_id) is not None
    assert LANGUAGES["en"]["welcome"] in chat.texts()
    assert set(chat.last_buttons()) == {"New reminder", "My reminders", "Language"}


async def test_ukrainian_telegram_setting_gives_ukrainian(harness: Harness) -> None:
    chat = harness.chat(language="uk")
    await chat.send("/start")
    assert LANGUAGES["uk"]["welcome"] in chat.texts()
    assert (await harness.repo.get_chat(chat.user_id)).language == "uk"


async def test_any_other_language_gives_english(harness: Harness) -> None:
    for user_id, language in [(1, "de"), (2, None), (3, "ru")]:
        chat = harness.chat(user_id=user_id, language=language)
        await chat.send("/start")
        assert LANGUAGES["en"]["welcome"] in chat.texts()


async def test_stored_language_is_not_overwritten_later(harness: Harness) -> None:
    await harness.chat(language="en").send("/start")
    await harness.chat(language="uk").send("/start")
    assert (await harness.repo.get_chat(1001)).language == "en"


async def test_help_mentions_kyiv_time(chat: FakeChat) -> None:
    await chat.send("/help")
    assert "Kyiv time" in chat.last_text


async def test_cancel_with_no_flow_changes_nothing(chat: FakeChat) -> None:
    await chat.send("/cancel")
    assert chat.last_text == LANGUAGES["en"]["nothing_to_cancel"]


async def test_channel_updates_are_ignored_and_store_nothing(
    chat: FakeChat, harness: Harness
) -> None:
    # Groups are served since 002; channels never are (002 FR-117).
    await chat.send("/start", chat_type="channel")
    assert await harness.repo.get_chat(chat.user_id) is None
    assert chat.texts() == []


async def test_plain_text_outside_a_flow_gets_a_hint(chat: FakeChat) -> None:
    await chat.send("hello")
    assert chat.last_text == LANGUAGES["en"]["unknown_input"]


async def test_old_button_answers_no_longer_available(chat: FakeChat, harness: Harness) -> None:
    await chat.press("rec:daily")
    assert harness.session.calls[-1].text == LANGUAGES["en"]["no_longer_available"]
