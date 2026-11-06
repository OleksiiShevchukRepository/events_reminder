"""Bot text in English and Ukrainian."""

from reminder_bot.i18n import en, uk

LANGUAGES = {"en": en.TEXT, "uk": uk.TEXT}


def translate(language: str, key: str, **values: object) -> str:
    return LANGUAGES[language][key].format(**values)


class Translator:
    """`translate` bound to one user's language."""

    def __init__(self, language: str) -> None:
        self.language = language

    def __call__(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)
