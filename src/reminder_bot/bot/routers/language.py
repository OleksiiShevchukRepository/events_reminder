"""Choosing the bot's language (FR-023a)."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from reminder_bot.bot import keyboards
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository, User

router = Router(name="language")


async def show(bot: Bot, user: User, t: Translator) -> None:
    await bot.send_message(user.id, t("language_prompt"), reply_markup=keyboards.languages())


@router.callback_query(F.data == "menu:language")
async def on_menu_language(
    callback: CallbackQuery, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    await state.clear()
    await bot.answer_callback_query(callback.id)
    await show(bot, user, t)


@router.callback_query(F.data.in_({"lang:en", "lang:uk"}))
async def on_language(
    callback: CallbackQuery, bot: Bot, state: FSMContext, user: User, repo: Repository
) -> None:
    language = callback.data.removeprefix("lang:")
    await state.clear()
    await repo.set_language(user.id, language)
    t = Translator(language)
    await bot.answer_callback_query(callback.id)
    await bot.send_message(user.id, t("language_changed"), reply_markup=keyboards.main_menu(t))
