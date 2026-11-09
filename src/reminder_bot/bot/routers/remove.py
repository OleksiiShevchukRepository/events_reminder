"""Removing a reminder after confirmation (001 FR-019).

In groups, the result names the member and repeats the removed text (002 FR-122).
"""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import end_flow
from reminder_bot.bot.screen import show_on_callback
from reminder_bot.bot.views import preview
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository

router = Router(name="remove")

_CONFIRMATION_PREVIEW_LENGTH = 1000


@router.callback_query(F.data.regexp(r"^msg:\d+:remove$"))
async def on_remove(
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
    text = t("remove_confirm", text=preview(message.text, _CONFIRMATION_PREVIEW_LENGTH))
    await show_on_callback(
        bot, ctx, repo, callback, text, keyboards.remove_confirmation(t, message.id)
    )


@router.callback_query(F.data.regexp(r"^msg:\d+:remove_yes$"))
async def on_remove_confirmed(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    message_id = int(callback.data.split(":")[1])
    message = await repo.get_message(ctx.chat_id, message_id)
    if message is None or not await repo.delete_message(ctx.chat_id, message_id):
        await bot.answer_callback_query(callback.id, t("no_longer_available"))
        return
    if ctx.is_group:
        text = t(
            "removed_by",
            name=ctx.member_name,
            text=preview(message.text, _CONFIRMATION_PREVIEW_LENGTH),
        )
    else:
        text = t("removed")
    await show_on_callback(bot, ctx, repo, callback, text, keyboards.main_menu(t))
