"""The guided flow for creating a message (contracts/bot-interface.md)."""

from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from reminder_bot.bot import keyboards
from reminder_bot.bot.states import CreateFlow
from reminder_bot.bot.views import summary
from reminder_bot.clock import Clock
from reminder_bot.domain.parsing import (
    date_not_past,
    datetime_in_future,
    parse_date,
    parse_interval,
    parse_text,
    parse_time,
)
from reminder_bot.domain.schedule import Recurrence, Rule
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import (
    MAX_ACTIVE_MESSAGES,
    LimitReached,
    Repository,
    User,
)

router = Router(name="create")


async def _prompt(bot: Bot, user: User, t: Translator, key: str) -> None:
    await bot.send_message(user.id, t(key), reply_markup=keyboards.cancel(t))


async def begin(bot: Bot, state: FSMContext, user: User, t: Translator, repo: Repository) -> None:
    await state.clear()
    if await repo.count_active(user.id) >= MAX_ACTIVE_MESSAGES:
        await bot.send_message(user.id, t("error_limit"), reply_markup=keyboards.main_menu(t))
        return
    await state.set_state(CreateFlow.recurrence)
    await bot.send_message(
        user.id, t("prompt_recurrence"), reply_markup=keyboards.recurrence_choices(t)
    )


@router.callback_query(F.data == "menu:new")
async def on_menu_new(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    await bot.answer_callback_query(callback.id)
    await begin(bot, state, user, t, repo)


@router.message(CreateFlow.recurrence)
async def on_typed_recurrence(message: Message, bot: Bot, user: User, t: Translator) -> None:
    await bot.send_message(
        user.id, t("error_choose_button"), reply_markup=keyboards.recurrence_choices(t)
    )


@router.callback_query(CreateFlow.recurrence, F.data.regexp(r"^rec:(\w+)$"))
async def on_recurrence(
    callback: CallbackQuery, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    await bot.answer_callback_query(callback.id)
    recurrence = Recurrence(callback.data.removeprefix("rec:"))
    await state.update_data(recurrence=recurrence.value)
    await state.set_state(CreateFlow.text)
    await _prompt(bot, user, t, "prompt_text")


@router.message(CreateFlow.text)
async def on_text(message: Message, bot: Bot, state: FSMContext, user: User, t: Translator) -> None:
    parsed = parse_text(message.text)
    if parsed.error:
        await _prompt(bot, user, t, parsed.error)
        return
    await state.update_data(text=parsed.value)
    recurrence = Recurrence((await state.get_data())["recurrence"])
    if recurrence is Recurrence.INTERVAL:
        await state.set_state(CreateFlow.interval)
        await _prompt(bot, user, t, "prompt_interval")
        return
    await state.set_state(CreateFlow.date)
    key = "prompt_date_once" if recurrence is Recurrence.ONCE else "prompt_date"
    await _prompt(bot, user, t, key)


@router.message(CreateFlow.interval)
async def on_interval(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator
) -> None:
    parsed = parse_interval(message.text or "")
    if parsed.error:
        await _prompt(bot, user, t, parsed.error)
        return
    await state.update_data(interval_days=parsed.value)
    await state.set_state(CreateFlow.date)
    await _prompt(bot, user, t, "prompt_date")


@router.message(CreateFlow.date)
async def on_date(
    message: Message, bot: Bot, state: FSMContext, user: User, t: Translator, clock: Clock
) -> None:
    parsed = parse_date(message.text or "")
    error = parsed.error or date_not_past(parsed.value, clock.now())
    if error:
        await _prompt(bot, user, t, error)
        return
    await state.update_data(start_date=parsed.value.isoformat())
    await state.set_state(CreateFlow.time)
    await _prompt(bot, user, t, "prompt_time")


@router.message(CreateFlow.time)
async def on_time(
    message: Message,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    now = clock.now()
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    parsed = parse_time(message.text or "")
    error = parsed.error or datetime_in_future(start_date, parsed.value, now)
    if error:
        await _prompt(bot, user, t, error)
        return

    await state.clear()
    rule = Rule(Recurrence(data["recurrence"]), start_date, parsed.value, data.get("interval_days"))
    try:
        saved = await repo.create_message(user.id, data["text"], rule, now)
    except LimitReached:
        await bot.send_message(user.id, t("error_limit"), reply_markup=keyboards.main_menu(t))
        return
    await bot.send_message(
        user.id, t("saved", summary=summary(t, saved)), reply_markup=keyboards.main_menu(t)
    )
