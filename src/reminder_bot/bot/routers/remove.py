"""Removing a message after confirmation (FR-019)."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from reminder_bot.bot import keyboards
from reminder_bot.bot.views import preview, show
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository, User

router = Router(name="remove")

_CONFIRMATION_PREVIEW_LENGTH = 1000


@router.callback_query(F.data.regexp(r"^msg:\d+:remove$"))
async def on_remove(
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
    text = t("remove_confirm", text=preview(message.text, _CONFIRMATION_PREVIEW_LENGTH))
    await show(bot, callback, text, keyboards.remove_confirmation(t, message.id))


@router.callback_query(F.data.regexp(r"^msg:\d+:remove_yes$"))
async def on_remove_confirmed(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    await state.clear()
    removed = await repo.delete_message(user.id, int(callback.data.split(":")[1]))
    if not removed:
        await bot.answer_callback_query(callback.id, t("no_longer_available"))
        return
    await show(bot, callback, t("removed"), keyboards.main_menu(t))
