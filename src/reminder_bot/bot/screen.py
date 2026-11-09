"""Keeping one screen in a private chat (002 FR-124).

A "screen" is the bot's latest menu, list, help, reminder screen or result, such as
"Saved." or "Cancelled.". In a private chat, showing a new screen deletes the previous
one and the command or text the person typed to get it, so the chat holds only the
current screen and the delivered reminders. Delivered reminders are never screens.

The current screen's IDs are stored with the chat, so this still works after a restart.
Telegram only deletes messages up to 48 hours old; older ones stay. Groups are unchanged.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.types import Message as TelegramMessage

from reminder_bot.bot.context import ChatContext
from reminder_bot.bot.flow import delete_messages
from reminder_bot.storage.repositories import Repository


async def send_screen(
    bot: Bot,
    ctx: ChatContext,
    repo: Repository,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    trigger: TelegramMessage | None = None,
    before: tuple[str, ...] = (),
) -> None:
    """Send a screen. `before` holds texts sent just ahead of it as part of the same
    screen, and `trigger` is the person's message that asked for it."""
    sent = [(await bot.send_message(text=part, **ctx.send_kwargs)).message_id for part in before]
    message = await bot.send_message(text=text, reply_markup=reply_markup, **ctx.send_kwargs)
    sent.append(message.message_id)
    if ctx.is_group:
        return
    await _replace(bot, ctx, repo, sent, trigger)


async def show_on_callback(
    bot: Bot,
    ctx: ChatContext,
    repo: Repository,
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Answer a button press by updating its message, or by sending a new screen.

    An updated message becomes the current screen, so pressing a button on an older
    message also clears the screen that was showing.
    """
    await bot.answer_callback_query(callback.id)
    message = callback.message
    if isinstance(message, TelegramMessage):
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as error:
            if "not modified" not in str(error):
                await send_screen(bot, ctx, repo, text, reply_markup)
                return
        if not ctx.is_group:
            await _replace(bot, ctx, repo, [message.message_id], None)
        return
    await send_screen(bot, ctx, repo, text, reply_markup)


async def _replace(
    bot: Bot,
    ctx: ChatContext,
    repo: Repository,
    current: list[int],
    trigger: TelegramMessage | None,
) -> None:
    previous = await repo.get_screen(ctx.chat_id)
    await repo.set_screen(ctx.chat_id, current)
    stale = [message_id for message_id in previous if message_id not in current]
    if trigger is not None:
        stale.append(trigger.message_id)
    if stale:
        await delete_messages(bot, ctx.chat_id, stale, "screen")
