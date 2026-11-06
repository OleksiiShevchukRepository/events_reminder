"""Inline buttons. Callback data follows contracts/bot-interface.md and fits in 64 bytes."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from reminder_bot.bot.views import preview
from reminder_bot.domain.schedule import Recurrence
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Message


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _rows(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[row for row in rows if row])


def main_menu(t: Translator) -> InlineKeyboardMarkup:
    return _rows(
        [_button(t("btn_new"), "menu:new")],
        [_button(t("btn_list"), "menu:list")],
        [_button(t("btn_language"), "menu:language")],
    )


def cancel(t: Translator) -> InlineKeyboardMarkup:
    return _rows([_button(t("btn_cancel"), "flow:cancel")])


def recurrence_choices(t: Translator) -> InlineKeyboardMarkup:
    return _rows(
        *[[_button(t(f"rec_{item.value}"), f"rec:{item.value}")] for item in Recurrence],
        [_button(t("btn_cancel"), "flow:cancel")],
    )


def languages() -> InlineKeyboardMarkup:
    return _rows([_button("English", "lang:en"), _button("Українська", "lang:uk")])


def message_list(
    t: Translator, messages: list[Message], first_number: int, page: int, pages: int
) -> InlineKeyboardMarkup:
    paging = []
    if page > 0:
        paging.append(_button(t("btn_previous"), f"page:{page - 1}"))
    if page < pages - 1:
        paging.append(_button(t("btn_next"), f"page:{page + 1}"))
    return _rows(
        *[
            [_button(f"{first_number + i}. {preview(m.text, 40)}", f"msg:{m.id}:open")]
            for i, m in enumerate(messages)
        ],
        paging,
        [_button(t("btn_new"), "menu:new")],
    )


def empty_list(t: Translator) -> InlineKeyboardMarkup:
    return _rows([_button(t("btn_new"), "menu:new")])


def message_screen(t: Translator, message: Message) -> InlineKeyboardMarkup:
    back = [_button(t("btn_back"), "page:0")]
    remove = [_button(t("btn_remove"), f"msg:{message.id}:remove")]
    if not message.is_active:
        return _rows(remove, back)
    date_label = "btn_edit_date_interval" if message.interval_days else "btn_edit_date"
    return _rows(
        [_button(t("btn_edit_text"), f"msg:{message.id}:edit_text")],
        [_button(t("btn_edit_recurrence"), f"msg:{message.id}:edit_rec")],
        [_button(t(date_label), f"msg:{message.id}:edit_date")],
        [_button(t("btn_edit_time"), f"msg:{message.id}:edit_time")],
        remove,
        back,
    )


def remove_confirmation(t: Translator, message_id: int) -> InlineKeyboardMarkup:
    return _rows(
        [_button(t("btn_remove_yes"), f"msg:{message_id}:remove_yes")],
        [_button(t("btn_keep"), f"msg:{message_id}:open")],
    )
