"""Formatting shared by the bot's screens and the scheduler."""

from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.types import Message as TelegramMessage

from reminder_bot.domain.parsing import MAX_TEXT_UTF16_UNITS
from reminder_bot.domain.schedule import KYIV
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Message

SUMMARY_PREVIEW_LENGTH = 200
LIST_PREVIEW_LENGTH = 60


def format_when(moment: datetime) -> str:
    local = moment.astimezone(KYIV)
    return f"{local.day}.{local.month}.{local.year} {local:%H:%M}"


def preview(text: str, length: int = LIST_PREVIEW_LENGTH) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= length else single_line[: length - 1] + "…"


def recurrence_label(t: Translator, message: Message) -> str:
    if message.interval_days is None:
        return t(f"rec_{message.recurrence.value}")
    if message.interval_days == 1:
        return t("rec_daily")
    return t("rec_every_n_days", days=message.interval_days)


def next_send_label(t: Translator, message: Message) -> str:
    if message.next_send_at is not None:
        return format_when(message.next_send_at)
    return t("next_sending") if message.is_active else t("next_none")


def status_label(t: Translator, message: Message) -> str:
    if message.not_delivered:
        return t("status_not_delivered")
    return t("status_active") if message.is_active else t("status_completed")


def summary(t: Translator, message: Message) -> str:
    return t(
        "summary",
        text=preview(message.text, SUMMARY_PREVIEW_LENGTH),
        recurrence=recurrence_label(t, message),
        time=message.send_time.strftime("%H:%M"),
        next_send=next_send_label(t, message),
    )


def message_details(t: Translator, message: Message, text: str) -> str:
    return t(
        "screen",
        text=text,
        recurrence=recurrence_label(t, message),
        time=message.send_time.strftime("%H:%M"),
        next_send=next_send_label(t, message),
        status=status_label(t, message),
    )


def fits_in_one_message(text: str) -> bool:
    return len(text.encode("utf-16-le")) // 2 <= MAX_TEXT_UTF16_UNITS


async def show(
    bot: Bot,
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Answer a button press by updating its message, or by sending a new one."""
    await bot.answer_callback_query(callback.id)
    message = callback.message
    if isinstance(message, TelegramMessage):
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as error:
            if "not modified" in str(error):
                return
        else:
            return
    await bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)
