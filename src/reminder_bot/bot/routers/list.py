"""The message list and each message's own screen (FR-014, FR-015)."""

import math

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from reminder_bot.bot import keyboards
from reminder_bot.bot.views import (
    SUMMARY_PREVIEW_LENGTH,
    fits_in_one_message,
    message_details,
    next_send_label,
    preview,
    recurrence_label,
    show,
    status_label,
)
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository, User

router = Router(name="list")

PAGE_SIZE = 5


async def show_list(
    bot: Bot,
    user: User,
    t: Translator,
    repo: Repository,
    page: int = 0,
    callback: CallbackQuery | None = None,
) -> None:
    messages, total = await repo.list_messages(user.id, page, PAGE_SIZE)
    pages = math.ceil(total / PAGE_SIZE)
    if total and page >= pages:
        page = pages - 1
        messages, total = await repo.list_messages(user.id, page, PAGE_SIZE)

    if total == 0:
        text, markup = t("list_empty"), keyboards.empty_list(t)
    else:
        first_number = page * PAGE_SIZE + 1
        entries = [
            t(
                "list_entry",
                number=first_number + index,
                preview=preview(message.text),
                recurrence=recurrence_label(t, message),
                time=message.send_time.strftime("%H:%M"),
                next_send=next_send_label(t, message),
                status=status_label(t, message),
            )
            for index, message in enumerate(messages)
        ]
        title = t("list_title", page=page + 1, pages=pages)
        text = "\n\n".join([title, *entries])
        markup = keyboards.message_list(t, messages, first_number, page, pages)

    if callback is None:
        await bot.send_message(user.id, text, reply_markup=markup)
    else:
        await show(bot, callback, text, markup)


@router.callback_query(F.data == "menu:list")
async def on_menu_list(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    await state.clear()
    await show_list(bot, user, t, repo, callback=callback)


@router.callback_query(F.data.regexp(r"^page:\d+$"))
async def on_page(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    await state.clear()
    page = int(callback.data.removeprefix("page:"))
    await show_list(bot, user, t, repo, page, callback)


@router.callback_query(F.data.regexp(r"^msg:\d+:open$"))
async def on_open(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    await state.clear()
    message = await repo.get_message(user.id, int(callback.data.split(":")[1]))
    if message is None:
        await bot.answer_callback_query(callback.id, t("no_longer_available"))
        return

    markup = keyboards.message_screen(t, message)
    details = message_details(t, message, message.text)
    if fits_in_one_message(details):
        await show(bot, callback, details, markup)
        return
    # The longest texts leave no room for details, so they get their own message first.
    await bot.answer_callback_query(callback.id)
    await bot.send_message(user.id, message.text)
    short = message_details(t, message, preview(message.text, SUMMARY_PREVIEW_LENGTH))
    await bot.send_message(user.id, short, reply_markup=markup)
