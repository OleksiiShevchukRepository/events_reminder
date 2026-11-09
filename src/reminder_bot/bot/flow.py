"""Asking a flow's questions, and cleaning up after a flow (002 FR-104, FR-119, FR-120).

Every flow keeps the IDs of the messages it produced: the bot's questions and error
replies, and the member's command and answers. They live in the flow's in-memory state,
so a flow lost on a restart leaves its messages behind, as the spec allows.

Every way a flow can end goes through `end_flow`, which deletes those messages. The
flow's final message is sent after it and isn't tracked, so it's the one that stays.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import ForceReply, InlineKeyboardMarkup, MessageEntity
from aiogram.types import Message as TelegramMessage
from aiogram.types import User as TelegramUser

from reminder_bot.bot import keyboards
from reminder_bot.bot.context import ChatContext
from reminder_bot.i18n import Translator

logger = logging.getLogger(__name__)

_BOT_MESSAGES = "bot_messages"
_MEMBER_MESSAGES = "member_messages"
# Telegram's limit for one deleteMessages call.
_DELETE_BATCH = 100


async def _track(state: FSMContext, key: str, message_id: int) -> None:
    data = await state.get_data()
    await state.update_data({key: [*data.get(key, []), message_id]})


async def track_member(state: FSMContext, message: TelegramMessage) -> None:
    """Remember a member's message in this flow, so it's deleted when the flow ends."""
    await _track(state, _MEMBER_MESSAGES, message.message_id)


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


async def ask(
    bot: Bot,
    state: FSMContext,
    ctx: ChatContext,
    t: Translator,
    text: str,
    buttons: InlineKeyboardMarkup | None = None,
) -> None:
    """Send one of the flow's questions or error replies, and track it for clean-up.

    A question answered with `buttons` shows them. Any other question expects typed
    text. In a private chat it gets a Cancel button. In a group it starts with the
    member's name and opens the reply box for them only; Telegram can't combine that
    with buttons, so it says to send /cancel instead (002 FR-104).
    """
    kwargs = dict(ctx.send_kwargs)
    if ctx.is_group:
        name = ctx.member_name
        text = f"{name}, {text[:1].lower()}{text[1:]}"
        kwargs["entities"] = [
            MessageEntity(
                type="text_mention",
                offset=0,
                length=_utf16_length(name),
                user=TelegramUser(id=ctx.member_id, is_bot=False, first_name=name),
            )
        ]
        if buttons is None:
            text = f"{text}\n\n{t('cancel_hint')}"
            reply_markup = ForceReply(force_reply=True, selective=True)
        else:
            reply_markup = buttons
    else:
        reply_markup = buttons or keyboards.cancel(t)
    sent = await bot.send_message(text=text, reply_markup=reply_markup, **kwargs)
    await _track(state, _BOT_MESSAGES, sent.message_id)


async def _delete(bot: Bot, chat_id: int, message_ids: list[int], whose: str) -> None:
    for start in range(0, len(message_ids), _DELETE_BATCH):
        batch = message_ids[start : start + _DELETE_BATCH]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=batch)
        except TelegramAPIError as error:
            # Too old, already deleted, or no right to delete members' messages. The
            # flow still ends normally (002 FR-120).
            logger.info(
                "flow_cleanup_skipped chat=%s whose=%s error=%s",
                chat_id,
                whose,
                type(error).__name__,
            )


async def end_flow(bot: Bot, state: FSMContext, ctx: ChatContext) -> None:
    """End whatever flow is in progress, deleting the messages it produced."""
    data = await state.get_data()
    await state.clear()
    # The bot's own messages first: deleting them never needs admin rights.
    if data.get(_BOT_MESSAGES):
        await _delete(bot, ctx.chat_id, data[_BOT_MESSAGES], "bot")
    if data.get(_MEMBER_MESSAGES):
        await _delete(bot, ctx.chat_id, data[_MEMBER_MESSAGES], "member")
