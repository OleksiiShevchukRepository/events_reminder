"""The guided flows for changing a reminder (contracts/bot-interface.md).

Nothing is saved until a flow's last step. The save re-checks the chat and status, so a
reminder that was removed or completed mid-flow is left alone. In groups, any member can
change any reminder, and the change records their name (002 FR-109, FR-121).
"""

from datetime import date, time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.types import Message as TelegramMessage

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import ask, end_flow, track_member
from reminder_bot.bot.screen import send_screen
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
from reminder_bot.storage.repositories import DateTimeInPast, Message, Repository

router = Router(name="update")


async def _prompt(bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator, key: str) -> None:
    await ask(bot, state, ctx, t, t(key))


async def _begin(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> Message | None:
    """Start an edit if this chat's reminder can still be changed."""
    await end_flow(bot, state, ctx)
    message = await repo.get_message(ctx.chat_id, int(callback.data.split(":")[1]))
    if message is None or not message.is_active:
        await bot.answer_callback_query(callback.id, t("no_longer_available"))
        return None
    await bot.answer_callback_query(callback.id)
    await state.update_data(message_id=message.id)
    return message


async def _current(state: FSMContext, ctx: ChatContext, repo: Repository) -> Message | None:
    data = await state.get_data()
    message = await repo.get_message(ctx.chat_id, data["message_id"])
    return message if message is not None and message.is_active else None


async def _stale(
    bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator, repo: Repository
) -> None:
    await end_flow(bot, state, ctx)
    await send_screen(bot, ctx, repo, t("no_longer_available"), keyboards.main_menu(t))


async def _finish(
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    saved: Message | None,
) -> None:
    if saved is None:
        await _stale(bot, state, ctx, t, repo)
        return
    await end_flow(bot, state, ctx)
    if ctx.is_group:
        text = t("updated_by", name=ctx.member_name, summary=summary(t, saved))
    else:
        text = t("updated", summary=summary(t, saved))
    await send_screen(bot, ctx, repo, text, keyboards.main_menu(t))


async def _save_schedule(
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
    message_id: int,
    rule: Rule,
) -> None:
    try:
        saved = await repo.update_schedule(
            ctx.chat_id, message_id, rule, clock.now(), ctx.creator_name
        )
    except DateTimeInPast:
        await _prompt(bot, state, ctx, t, "error_datetime_past")
        return
    await _finish(bot, state, ctx, t, repo, saved)


# Text


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_text$"))
async def on_edit_text(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, ctx, t, repo):
        await state.set_state(UpdateFlow.text)
        await _prompt(bot, state, ctx, t, "prompt_new_text")


@router.message(UpdateFlow.text)
async def on_new_text(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await track_member(state, message)
    parsed = parse_text(message.text)
    if parsed.error:
        await _prompt(bot, state, ctx, t, parsed.error)
        return
    data = await state.get_data()
    saved = await repo.update_text(
        ctx.chat_id, data["message_id"], parsed.value, clock.now(), ctx.creator_name
    )
    await _finish(bot, state, ctx, t, repo, saved)


# Time


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_time$"))
async def on_edit_time(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, ctx, t, repo):
        await state.set_state(UpdateFlow.time)
        await _prompt(bot, state, ctx, t, "prompt_new_time")


@router.message(UpdateFlow.time)
async def on_new_time(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await track_member(state, message)
    parsed = parse_time(message.text or "")
    if parsed.error:
        await _prompt(bot, state, ctx, t, parsed.error)
        return
    current = await _current(state, ctx, repo)
    if current is None:
        await _stale(bot, state, ctx, t, repo)
        return
    if current.recurrence is Recurrence.ONCE:
        error = datetime_in_future(current.start_date, parsed.value, clock.now())
        if error:
            await _prompt(bot, state, ctx, t, error)
            return
    # A recurring message keeps its start date, and moves to its next date at the new time.
    rule = Rule(current.recurrence, current.start_date, parsed.value, current.interval_days)
    await _save_schedule(bot, state, ctx, t, repo, clock, current.id, rule)


# Date, or date and interval together (FR-016a)


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_date$"))
async def on_edit_date(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, ctx, t, repo):
        await state.set_state(UpdateFlow.date)
        await _prompt(bot, state, ctx, t, "prompt_new_date")


@router.message(UpdateFlow.date)
async def on_new_date(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await track_member(state, message)
    now = clock.now()
    parsed = parse_date(message.text or "")
    error = parsed.error or date_not_past(parsed.value, now)
    if error:
        await _prompt(bot, state, ctx, t, error)
        return
    current = await _current(state, ctx, repo)
    if current is None:
        await _stale(bot, state, ctx, t, repo)
        return

    new_date = parsed.value
    data = await state.get_data()
    target = data.get("target")
    if target is not None:
        # Switching to "only once" or "every N days".
        if datetime_in_future(new_date, current.send_time, now):
            await state.update_data(new_date=new_date.isoformat())
            await state.set_state(UpdateFlow.switch_time)
            await _prompt(bot, state, ctx, t, "prompt_new_time")
            return
        rule = Rule(Recurrence(target), new_date, current.send_time, data.get("interval_days"))
        await _save_schedule(bot, state, ctx, t, repo, clock, current.id, rule)
        return

    error = datetime_in_future(new_date, current.send_time, now)
    if error:
        await _prompt(bot, state, ctx, t, error)
        return
    if current.recurrence is Recurrence.INTERVAL:
        await state.update_data(new_date=new_date.isoformat())
        await state.set_state(UpdateFlow.interval)
        await _prompt(bot, state, ctx, t, "prompt_new_interval")
        return
    rule = Rule(current.recurrence, new_date, current.send_time)
    await _save_schedule(bot, state, ctx, t, repo, clock, current.id, rule)


@router.message(UpdateFlow.interval)
async def on_new_interval(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await track_member(state, message)
    parsed = parse_interval(message.text or "")
    if parsed.error:
        await _prompt(bot, state, ctx, t, parsed.error)
        return
    data = await state.get_data()
    if data.get("target") is not None:
        await state.update_data(interval_days=parsed.value)
        await state.set_state(UpdateFlow.date)
        await _prompt(bot, state, ctx, t, "prompt_new_date")
        return
    current = await _current(state, ctx, repo)
    if current is None:
        await _stale(bot, state, ctx, t, repo)
        return
    new_date = date.fromisoformat(data["new_date"])
    rule = Rule(Recurrence.INTERVAL, new_date, current.send_time, parsed.value)
    await _save_schedule(bot, state, ctx, t, repo, clock, current.id, rule)


# Recurrence


@router.callback_query(F.data.regexp(r"^msg:\d+:edit_rec$"))
async def on_edit_recurrence(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    if await _begin(callback, bot, state, ctx, t, repo):
        await state.set_state(UpdateFlow.recurrence)
        await ask(bot, state, ctx, t, t("prompt_new_recurrence"), keyboards.recurrence_choices(t))


@router.message(UpdateFlow.recurrence)
async def on_typed_recurrence(
    message: TelegramMessage, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    await track_member(state, message)
    await ask(bot, state, ctx, t, t("error_choose_button"), keyboards.recurrence_choices(t))


@router.callback_query(UpdateFlow.recurrence, F.data.regexp(r"^rec:\w+$"))
async def on_new_recurrence(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await bot.answer_callback_query(callback.id)
    target = Recurrence(callback.data.removeprefix("rec:"))
    if target is Recurrence.ONCE:
        await state.update_data(target=target.value)
        await state.set_state(UpdateFlow.date)
        await _prompt(bot, state, ctx, t, "prompt_new_date")
        return
    if target is Recurrence.INTERVAL:
        await state.update_data(target=target.value)
        await state.set_state(UpdateFlow.interval)
        await _prompt(bot, state, ctx, t, "prompt_new_interval")
        return
    current = await _current(state, ctx, repo)
    if current is None:
        await _stale(bot, state, ctx, t, repo)
        return
    rule = Rule(target, current.start_date, current.send_time)
    await _save_schedule(bot, state, ctx, t, repo, clock, current.id, rule)


@router.message(UpdateFlow.switch_time)
async def on_switch_time(
    message: TelegramMessage,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await track_member(state, message)
    data = await state.get_data()
    new_date = date.fromisoformat(data["new_date"])
    parsed = parse_time(message.text or "")
    error = parsed.error or datetime_in_future(new_date, parsed.value, clock.now())
    if error:
        await _prompt(bot, state, ctx, t, error)
        return
    send_time: time = parsed.value
    rule = Rule(Recurrence(data["target"]), new_date, send_time, data.get("interval_days"))
    await _save_schedule(bot, state, ctx, t, repo, clock, data["message_id"], rule)
