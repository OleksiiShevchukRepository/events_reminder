"""Whatever no other handler took. This router comes last."""

import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import end_flow
from reminder_bot.bot.screen import send_screen
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository

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
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    if await state.get_state() is None:
        await bot.answer_callback_query(callback.id, t(_stale_answer(ctx, callback)))
        return
    await end_flow(bot, state, ctx)
    await bot.answer_callback_query(callback.id)
    await send_screen(bot, ctx, repo, t("cancelled"), keyboards.main_menu(t))


@router.callback_query()
async def on_stale_button(
    callback: CallbackQuery, bot: Bot, ctx: ChatContext, t: Translator
) -> None:
    """A button from a finished flow, from before a restart, or from someone else's flow."""
    await bot.answer_callback_query(callback.id, t(_stale_answer(ctx, callback)))


@router.message()
async def on_unknown_message(
    message: Message, bot: Bot, ctx: ChatContext, t: Translator, repo: Repository
) -> None:
    # In groups the bot never answers ordinary chat (002 FR-113).
    if ctx.is_group:
        return
    await send_screen(bot, ctx, repo, t("unknown_input"), keyboards.main_menu(t), trigger=message)
