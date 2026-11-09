"""The reminder list and each reminder's own screen (001 FR-014, FR-015; 002 FR-107).

Lists are scoped to the chat they're asked in, so a group sees only its own reminders.
"""

import math

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import end_flow
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
from reminder_bot.storage.repositories import Repository

router = Router(name="list")

PAGE_SIZE = 10


async def show_list(
    bot: Bot,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    page: int = 0,
    callback: CallbackQuery | None = None,
) -> None:
    messages, total = await repo.list_messages(ctx.chat_id, page, PAGE_SIZE)
    pages = math.ceil(total / PAGE_SIZE)
    if total and page >= pages:
        page = pages - 1
        messages, total = await repo.list_messages(ctx.chat_id, page, PAGE_SIZE)

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
        await bot.send_message(text=text, reply_markup=markup, **ctx.send_kwargs)
    else:
        await show(bot, callback, text, markup)


@router.callback_query(F.data == "menu:list")
async def on_menu_list(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    await show_list(bot, ctx, t, repo, callback=callback)


@router.callback_query(F.data.regexp(r"^page:\d+$"))
async def on_page(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    page = int(callback.data.removeprefix("page:"))
    await show_list(bot, ctx, t, repo, page, callback)


@router.callback_query(F.data.regexp(r"^msg:\d+:open$"))
async def on_open(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    message = await repo.get_message(ctx.chat_id, int(callback.data.split(":")[1]))
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
    await bot.send_message(text=message.text, **ctx.send_kwargs)
    short = message_details(t, message, preview(message.text, SUMMARY_PREVIEW_LENGTH))
    await bot.send_message(text=short, reply_markup=markup, **ctx.send_kwargs)
