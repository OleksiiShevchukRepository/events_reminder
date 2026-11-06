"""Commands. This router comes first, so a command works even in the middle of a flow."""

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from reminder_bot.bot import keyboards
from reminder_bot.bot.routers import create, language
from reminder_bot.bot.routers import list as message_list
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository, User

router = Router(name="commands")


@router.message(CommandStart())
async def on_start(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    await state.clear()
    await bot.send_message(user.id, t("welcome"), reply_markup=keyboards.main_menu(t))


@router.message(Command("help"))
async def on_help(message: Message, bot: Bot, state: FSMContext, user: User, t: Translator) -> None:
    await state.clear()
    await bot.send_message(user.id, t("help"), reply_markup=keyboards.main_menu(t))


@router.message(Command("cancel"))
async def on_cancel(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    key = "cancelled" if await state.get_state() else "nothing_to_cancel"
    await state.clear()
    await bot.send_message(user.id, t(key), reply_markup=keyboards.main_menu(t))


@router.message(Command("new"))
async def on_new(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator, repo: Repository
) -> None:
    await create.begin(bot, state, user, t, repo)


@router.message(Command("list"))
async def on_list(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator, repo: Repository
) -> None:
    await state.clear()
    await message_list.show_list(bot, user, t, repo)


@router.message(Command("language"))
async def on_language(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    await state.clear()
    await language.show(bot, user, t)
