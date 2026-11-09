"""Choosing the bot's language (001 FR-023a). In a group, any member sets it for the
whole group (002 FR-110, FR-111).
"""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import end_flow
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository

router = Router(name="language")


async def show(bot: Bot, ctx: ChatContext, t: Translator) -> None:
    await bot.send_message(
        text=t("language_prompt"), reply_markup=keyboards.languages(), **ctx.send_kwargs
    )


@router.callback_query(F.data == "menu:language")
async def on_menu_language(
    callback: CallbackQuery, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    await end_flow(bot, state, ctx)
    await bot.answer_callback_query(callback.id)
    await show(bot, ctx, t)


@router.callback_query(F.data.in_({"lang:en", "lang:uk"}))
async def on_language(
    callback: CallbackQuery, bot: Bot, state: FSMContext, ctx: ChatContext, repo: Repository
) -> None:
    language = callback.data.removeprefix("lang:")
    await end_flow(bot, state, ctx)
    await repo.set_language(ctx.chat_id, language)
    t = Translator(language)
    await bot.answer_callback_query(callback.id)
    await bot.send_message(
        text=t("language_changed"), reply_markup=keyboards.main_menu(t), **ctx.send_kwargs
    )
