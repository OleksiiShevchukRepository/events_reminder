"""Whatever no other handler took. This router comes last."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from reminder_bot.bot import keyboards
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import User

router = Router(name="fallback")


@router.callback_query(F.data == "flow:cancel")
async def on_cancel_button(
    callback: CallbackQuery, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    if await state.get_state() is None:
        await bot.answer_callback_query(callback.id, t("no_longer_available"))
        return
    await state.clear()
    await bot.answer_callback_query(callback.id)
    await bot.send_message(user.id, t("cancelled"), reply_markup=keyboards.main_menu(t))


@router.callback_query()
async def on_stale_button(callback: CallbackQuery, bot: Bot, t: Translator) -> None:
    """A button from a finished flow, or from before a restart."""
    await bot.answer_callback_query(callback.id, t("no_longer_available"))


@router.message()
async def on_unknown_message(message: Message, bot: Bot, user: User, t: Translator) -> None:
    await bot.send_message(user.id, t("unknown_input"), reply_markup=keyboards.main_menu(t))
