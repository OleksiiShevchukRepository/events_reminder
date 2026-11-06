"""The guided flows for changing a message (contracts/bot-interface.md).

Nothing is saved until a flow's last step. The save re-checks the owner and status,
so a message that was removed or completed mid-flow is left alone.
"""

from datetime import date, time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.types import Message as TelegramMessage

from reminder_bot.bot import keyboards
from reminder_bot.bot.states import UpdateFlow
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
    DateTimeInPast,
    Message,
    Repository,
    User,
)

router = Router(name="update")


async def _prompt(bot: Bot, user: User, t: Translator, key: str) -> None:
    await bot.send_message(user.id, t(key), reply_markup=keyboards.cancel(t))


async def _begin(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> Message | None:
    """Start an edit if this user's message can still be changed."""
    await state.clear()
    message = await repo.get_message(user.id, int(callback.data.split(":")[1]))
    if message is None or not message.is_active:
        await bot.answer_callback_query(callback.id, t("no_longer_available"))
        return None
    await bot.answer_callback_query(callback.id)
    await state.update_data(message_id=message.id)
    return message


async def _current(state: FSMContext, user: User, repo: Repository) -> Message | None:
    data = await state.get_data()
    message = await repo.get_message(user.id, data["message_id"])
    return message if message is not None and message.is_active else None


async def _stale(bot: Bot, state: FSMContext, user: User, t: Translator) -> None:
    await state.clear()
    await bot.send_message(user.id, t("no_longer_available"), reply_markup=keyboards.main_menu(t))


async def _finish(
    bot: Bot, state: FSMContext, user: User, t: Translator, saved: Message | None
) -> None:
    if saved is None:
        await _stale(bot, state, user, t)
        return
    await state.clear()
    await bot.send_message(
        user.id, t("updated", summary=summary(t, saved)), reply_markup=keyboards.main_menu(t)
    )


async def _save_schedule(
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
    message_id: int,
    rule: Rule,
) -> None:
    try:
        saved = await repo.update_schedule(user.id, message_id, rule, clock.now())
    except DateTimeInPast:
        await _prompt(bot, user, t, "error_datetime_past")
        return
    await _finish(bot, state, user, t, saved)


# Text


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_text$"))
async def on_edit_text(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, user, t, repo):
        await state.set_state(UpdateFlow.text)
        await _prompt(bot, user, t, "prompt_new_text")


@router.message(UpdateFlow.text)
async def on_new_text(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    parsed = parse_text(message.text)
    if parsed.error:
        await _prompt(bot, user, t, parsed.error)
        return
    data = await state.get_data()
    saved = await repo.update_text(user.id, data["message_id"], parsed.value, clock.now())
    await _finish(bot, state, user, t, saved)


# Time


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_time$"))
async def on_edit_time(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, user, t, repo):
        await state.set_state(UpdateFlow.time)
        await _prompt(bot, user, t, "prompt_new_time")


@router.message(UpdateFlow.time)
async def on_new_time(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    parsed = parse_time(message.text or "")
    if parsed.error:
        await _prompt(bot, user, t, parsed.error)
        return
    current = await _current(state, user, repo)
    if current is None:
        await _stale(bot, state, user, t)
        return
    if current.recurrence is Recurrence.ONCE:
        error = datetime_in_future(current.start_date, parsed.value, clock.now())
        if error:
            await _prompt(bot, user, t, error)
            return
    # A recurring message keeps its start date, and moves to its next date at the new time.
    rule = Rule(current.recurrence, current.start_date, parsed.value, current.interval_days)
    await _save_schedule(bot, state, user, t, repo, clock, current.id, rule)


# Date, or date and interval together (FR-016a)


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_date$"))
async def on_edit_date(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, user, t, repo):
        await state.set_state(UpdateFlow.date)
        await _prompt(bot, user, t, "prompt_new_date")


@router.message(UpdateFlow.date)
async def on_new_date(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    now = clock.now()
    parsed = parse_date(message.text or "")
    error = parsed.error or date_not_past(parsed.value, now)
    if error:
        await _prompt(bot, user, t, error)
        return
    current = await _current(state, user, repo)
    if current is None:
        await _stale(bot, state, user, t)
        return

    new_date = parsed.value
    data = await state.get_data()
    target = data.get("target")
    if target is not None:
        # Switching to "only once" or "every N days".
        if datetime_in_future(new_date, current.send_time, now):
            await state.update_data(new_date=new_date.isoformat())
            await state.set_state(UpdateFlow.switch_time)
            await _prompt(bot, user, t, "prompt_new_time")
            return
        rule = Rule(Recurrence(target), new_date, current.send_time, data.get("interval_days"))
        await _save_schedule(bot, state, user, t, repo, clock, current.id, rule)
        return

    error = datetime_in_future(new_date, current.send_time, now)
    if error:
        await _prompt(bot, user, t, error)
        return
    if current.recurrence is Recurrence.INTERVAL:
        await state.update_data(new_date=new_date.isoformat())
        await state.set_state(UpdateFlow.interval)
        await _prompt(bot, user, t, "prompt_new_interval")
        return
    rule = Rule(current.recurrence, new_date, current.send_time)
    await _save_schedule(bot, state, user, t, repo, clock, current.id, rule)


@router.message(UpdateFlow.interval)
async def on_new_interval(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    parsed = parse_interval(message.text or "")
    if parsed.error:
        await _prompt(bot, user, t, parsed.error)
        return
    data = await state.get_data()
    if data.get("target") is not None:
        await state.update_data(interval_days=parsed.value)
        await state.set_state(UpdateFlow.date)
        await _prompt(bot, user, t, "prompt_new_date")
        return
    current = await _current(state, user, repo)
    if current is None:
        await _stale(bot, state, user, t)
        return
    new_date = date.fromisoformat(data["new_date"])
    rule = Rule(Recurrence.INTERVAL, new_date, current.send_time, parsed.value)
    await _save_schedule(bot, state, user, t, repo, clock, current.id, rule)


# Recurrence


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_rec$"))
async def on_edit_recurrence(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, user, t, repo):
        await state.set_state(UpdateFlow.recurrence)
        await bot.send_message(
            user.id, t("prompt_new_recurrence"), reply_markup=keyboards.recurrence_choices(t)
        )


@router.message(UpdateFlow.recurrence)
async def on_typed_recurrence(
    message: TelegramMessage, bot: Bot, user: User, t: Translator
) -> None:
    await bot.send_message(
        user.id, t("error_choose_button"), reply_markup=keyboards.recurrence_choices(t)
    )


@router.callback_query(UpdateFlow.recurrence, F.data.regexp(r"^rec:\w+$"))
async def on_new_recurrence(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await bot.answer_callback_query(callback.id)
    target = Recurrence(callback.data.removeprefix("rec:"))
    if target is Recurrence.ONCE:
        await state.update_data(target=target.value)
        await state.set_state(UpdateFlow.date)
        await _prompt(bot, user, t, "prompt_new_date")
        return
    if target is Recurrence.INTERVAL:
        await state.update_data(target=target.value)
        await state.set_state(UpdateFlow.interval)
        await _prompt(bot, user, t, "prompt_new_interval")
        return
    current = await _current(state, user, repo)
    if current is None:
        await _stale(bot, state, user, t)
        return
    rule = Rule(target, current.start_date, current.send_time)
    await _save_schedule(bot, state, user, t, repo, clock, current.id, rule)


@router.message(UpdateFlow.switch_time)
async def on_switch_time(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    user: User,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    data = await state.get_data()
    new_date = date.fromisoformat(data["new_date"])
    parsed = parse_time(message.text or "")
    error = parsed.error or datetime_in_future(new_date, parsed.value, clock.now())
    if error:
        await _prompt(bot, user, t, error)
        return
    send_time: time = parsed.value
    rule = Rule(Recurrence(data["target"]), new_date, send_time, data.get("interval_days"))
    await _save_schedule(bot, state, user, t, repo, clock, data["message_id"], rule)
