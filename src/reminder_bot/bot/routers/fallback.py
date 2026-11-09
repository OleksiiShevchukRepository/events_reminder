"""Whatever no other handler took. This router comes last."""

import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import end_flow
from reminder_bot.i18n import Translator

router = Router(name="fallback")

# Buttons that belong to one member's flow. A flow is keyed by member, so another
# member pressing one has no flow and lands here (002 FR-105).
_FLOW_BUTTON = re.compile(r"^(rec:\w+|flow:cancel)$")


def _stale_answer(ctx: ChatContext, callback: CallbackQuery) -> str:
    if ctx.is_group and _FLOW_BUTTON.match(callback.data or ""):
        return "not_your_request"
    return "no_longer_available"


@router.callback_query(F.data == "flow:cancel")
async def on_cancel_button(
    callback: CallbackQuery, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    if await state.get_state() is None:
        await bot.answer_callback_query(callback.id, t(_stale_answer(ctx, callback)))
        return
    await end_flow(bot, state, ctx)
    await bot.answer_callback_query(callback.id)
    await bot.send_message(
        text=t("cancelled"), reply_markup=keyboards.main_menu(t), **ctx.send_kwargs
    )


@router.callback_query()
async def on_stale_button(
    callback: CallbackQuery, bot: Bot, ctx: ChatContext, t: Translator
) -> None:
    """A button from a finished flow, from before a restart, or from someone else's flow."""
    await bot.answer_callback_query(callback.id, t(_stale_answer(ctx, callback)))


@router.message()
async def on_unknown_message(message: Message, bot: Bot, ctx: ChatContext, t: Translator) -> None:
    # In groups the bot never answers ordinary chat (002 FR-113).
    if ctx.is_group:
        return
    await bot.send_message(
        text=t("unknown_input"), reply_markup=keyboards.main_menu(t), **ctx.send_kwargs
    )
