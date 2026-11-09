"""Commands. This router comes first, so a command works even in the middle of a flow.

A command ends any flow in progress, cleaning up its messages (002 FR-119).
"""

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import end_flow, track_member
from reminder_bot.bot.routers import create, language
from reminder_bot.bot.routers import list as message_list
from reminder_bot.bot.screen import send_screen
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository

router = Router(name="commands")


def _help_key(ctx: ChatContext, private_key: str) -> str:
    return "help_group" if ctx.is_group else private_key


@router.message(CommandStart())
async def on_start(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    await send_screen(
        bot, ctx, repo, t(_help_key(ctx, "welcome")), keyboards.main_menu(t), trigger=message
    )


@router.message(Command("help"))
async def on_help(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    await send_screen(
        bot, ctx, repo, t(_help_key(ctx, "help")), keyboards.main_menu(t), trigger=message
    )


@router.message(Command("cancel"))
async def on_cancel(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    in_flow = await state.get_state() is not None
    if in_flow:
        await track_member(state, message)
    await end_flow(bot, state, ctx)
    await send_screen(
        bot,
        ctx,
        repo,
        t("cancelled" if in_flow else "nothing_to_cancel"),
        keyboards.main_menu(t),
        # Inside a flow, the command was deleted with the flow's other messages.
        trigger=None if in_flow else message,
    )


@router.message(Command("new"))
async def on_new(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await create.begin(bot, state, ctx, t, repo, command=message)


@router.message(Command("list"))
async def on_list(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    await message_list.show_list(bot, ctx, t, repo, trigger=message)


@router.message(Command("language"))
async def on_language(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await end_flow(bot, state, ctx)
    await language.show(bot, ctx, t, repo, trigger=message)
