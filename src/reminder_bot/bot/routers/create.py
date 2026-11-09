"""The guided flow for creating a reminder (contracts/bot-interface.md).

In groups, the reminder belongs to the group and records who created it (002 FR-102,
FR-121). Every question goes through `flow.ask`, and every answer is tracked, so the flow
can clean up after itself (FR-119).
"""

from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import ask, end_flow, track_member
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
from reminder_bot.storage.repositories import MAX_ACTIVE_MESSAGES, LimitReached, Repository

router = Router(name="create")


async def begin(
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    command: Message | None = None,
) -> None:
    await end_flow(bot, state, ctx)
    if await repo.count_active(ctx.chat_id) >= MAX_ACTIVE_MESSAGES:
        await bot.send_message(
            text=t("error_limit"), reply_markup=keyboards.main_menu(t), **ctx.send_kwargs
        )
        return
    await state.set_state(CreateFlow.recurrence)
    if command is not None:
        await track_member(state, command)
    await ask(bot, state, ctx, t, t("prompt_recurrence"), keyboards.recurrence_choices(t))


@router.callback_query(F.data == "menu:new")
async def on_menu_new(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
) -> None:
    await bot.answer_callback_query(callback.id)
    await begin(bot, state, ctx, t, repo)


@router.message(CreateFlow.recurrence)
async def on_typed_recurrence(
    message: Message, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    await track_member(state, message)
    await ask(bot, state, ctx, t, t("error_choose_button"), keyboards.recurrence_choices(t))


@router.callback_query(CreateFlow.recurrence, F.data.regexp(r"^rec:(\w+)$"))
async def on_recurrence(
    callback: CallbackQuery, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    await bot.answer_callback_query(callback.id)
    recurrence = Recurrence(callback.data.removeprefix("rec:"))
    await state.update_data(recurrence=recurrence.value)
    await state.set_state(CreateFlow.text)
    await ask(bot, state, ctx, t, t("prompt_text"))


@router.message(CreateFlow.text)
async def on_text(
    message: Message, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    await track_member(state, message)
    parsed = parse_text(message.text)
    if parsed.error:
        await ask(bot, state, ctx, t, t(parsed.error))
        return
    await state.update_data(text=parsed.value)
    recurrence = Recurrence((await state.get_data())["recurrence"])
    if recurrence is Recurrence.INTERVAL:
        await state.set_state(CreateFlow.interval)
        await ask(bot, state, ctx, t, t("prompt_interval"))
        return
    await state.set_state(CreateFlow.date)
    key = "prompt_date_once" if recurrence is Recurrence.ONCE else "prompt_date"
    await ask(bot, state, ctx, t, t(key))


@router.message(CreateFlow.interval)
async def on_interval(
    message: Message, bot: Bot, state: FSMContext, ctx: ChatContext, t: Translator
) -> None:
    await track_member(state, message)
    parsed = parse_interval(message.text or "")
    if parsed.error:
        await ask(bot, state, ctx, t, t(parsed.error))
        return
    await state.update_data(interval_days=parsed.value)
    await state.set_state(CreateFlow.date)
    await ask(bot, state, ctx, t, t("prompt_date"))


@router.message(CreateFlow.date)
async def on_date(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    clock: Clock,
) -> None:
    await track_member(state, message)
    parsed = parse_date(message.text or "")
    error = parsed.error or date_not_past(parsed.value, clock.now())
    if error:
        await ask(bot, state, ctx, t, t(error))
        return
    await state.update_data(start_date=parsed.value.isoformat())
    await state.set_state(CreateFlow.time)
    await ask(bot, state, ctx, t, t("prompt_time"))


@router.message(CreateFlow.time)
async def on_time(
    message: Message,
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    repo: Repository,
    clock: Clock,
) -> None:
    await track_member(state, message)
    now = clock.now()
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    parsed = parse_time(message.text or "")
    error = parsed.error or datetime_in_future(start_date, parsed.value, now)
    if error:
        await ask(bot, state, ctx, t, t(error))
        return

    await end_flow(bot, state, ctx)
    rule = Rule(Recurrence(data["recurrence"]), start_date, parsed.value, data.get("interval_days"))
    try:
        saved = await repo.create_message(ctx.chat_id, data["text"], rule, now, ctx.creator_name)
    except LimitReached:
        await bot.send_message(
            text=t("error_limit"), reply_markup=keyboards.main_menu(t), **ctx.send_kwargs
        )
        return
    if ctx.is_group:
        text = t("saved_by", name=ctx.member_name, summary=summary(t, saved))
    else:
        text = t("saved", summary=summary(t, saved))
    await bot.send_message(text=text, reply_markup=keyboards.main_menu(t), **ctx.send_kwargs)
