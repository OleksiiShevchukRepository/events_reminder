from conftest import FakeChat, Harness
from reminder_bot.i18n import LANGUAGES


async def test_language_offers_both_languages(chat: FakeChat) -> None:
    await chat.send("/language")
    assert chat.last_text == LANGUAGES["en"]["language_prompt"]
    assert chat.last_buttons() == {"English": "lang:en", "Українська": "lang:uk"}


async def test_menu_button_offers_languages(chat: FakeChat) -> None:
    await chat.press("menu:language")
    assert chat.last_buttons() == {"English": "lang:en", "Українська": "lang:uk"}


async def test_later_text_uses_the_chosen_language(chat: FakeChat, harness: Harness) -> None:
    await chat.send("/language")
    await chat.press("lang:uk")
    assert LANGUAGES["uk"]["language_changed"] in chat.texts()
    assert (await harness.repo.get_user(chat.user_id)).language == "uk"
    await chat.send("/help")
    assert LANGUAGES["uk"]["help"] in chat.texts()


async def test_chosen_language_survives_a_different_telegram_setting(
    harness: Harness,
) -> None:
    chat = harness.chat(language="uk")
    await chat.send("/language")
    await chat.press("lang:en")
    await chat.send("/help")
    assert chat.last_text == LANGUAGES["en"]["help"]


async def test_reminder_text_is_unchanged_by_a_language_change(
    chat: FakeChat, harness: Harness
) -> None:
    await chat.send("/new")
    await chat.press("rec:once")
    await chat.send("Pay rent")
    await chat.send("7.11.2026")
    await chat.send("14:45")
    await chat.send("/language")
    await chat.press("lang:uk")
    messages, _ = await harness.repo.list_messages(chat.user_id, 0, 10)
    assert messages[0].text == "Pay rent"


async def test_language_change_ends_a_flow(chat: FakeChat) -> None:
    await chat.send("/new")
    await chat.send("/language")
    await chat.press("lang:en")
    await chat.send("hello")
    assert chat.last_text == LANGUAGES["en"]["unknown_input"]
