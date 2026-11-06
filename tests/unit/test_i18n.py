from string import Formatter

from reminder_bot.i18n import LANGUAGES, Translator


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def test_languages_have_identical_keys() -> None:
    assert set(LANGUAGES["en"]) == set(LANGUAGES["uk"])


def test_languages_have_identical_placeholders() -> None:
    for key, english in LANGUAGES["en"].items():
        assert placeholders(english) == placeholders(LANGUAGES["uk"][key]), key


def test_translator_fills_in_values() -> None:
    assert Translator("en")("rec_every_n_days", days=10) == "Every 10 days"
    assert "10" in Translator("uk")("rec_every_n_days", days=10)


def test_values_containing_braces_are_not_reformatted() -> None:
    assert Translator("en")("removed") == "Removed."
    text = Translator("en")("saved", summary="{not a placeholder}")
    assert "{not a placeholder}" in text
