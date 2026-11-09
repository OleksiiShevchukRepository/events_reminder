"""Runs before handlers: which chats are served, and who is asking."""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update

from reminder_bot.bot.context import ChatContext, display_name
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

GROUP_TYPES = {"group", "supergroup"}
COMMANDS = {"start", "help", "new", "list", "language", "cancel"}
# Commands and buttons that start or change something. Anonymous admins can't use them,
# because their messages and their button presses arrive as different senders.
_ANONYMOUS_BLOCKED_COMMANDS = {"new", "language"}
_ANONYMOUS_BLOCKED_BUTTONS = re.compile(
    r"^(menu:new|menu:language|lang:\w+|msg:\d+:(edit_\w+|remove|remove_yes))$"
)
_COMMAND = re.compile(r"^/([A-Za-z0-9_]+)(?:@([A-Za-z0-9_]+))?(?:\s|$)")
_MEMBER_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
}


def _chat_of(event: TelegramObject) -> Chat | None:
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat
    return None


def _thread_of(event: TelegramObject) -> int | None:
    message = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(message, Message) and message.is_topic_message:
        return message.message_thread_id
    return None


async def command_for_this_bot(message: Message, bot: Bot) -> str | None:
    """The command's name, if the message is one of this bot's commands."""
    match = _COMMAND.match(message.text or "")
    if match is None or match.group(1).lower() not in COMMANDS:
        return None
    mention = match.group(2)
    if mention is not None and mention.lower() != ((await bot.me()).username or "").lower():
        return None
    return match.group(1).lower()


async def _is_current_member(bot: Bot, chat_id: int, user_id: int) -> tuple[bool, bool]:
    """Whether a user is in the group now, and whether they're an anonymous admin."""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramAPIError:
        return False, False
    anonymous = bool(getattr(member, "is_anonymous", False))
    if member.status in _MEMBER_STATUSES:
        return True, anonymous
    return member.status == ChatMemberStatus.RESTRICTED and bool(member.is_member), anonymous


class ChatContextMiddleware(BaseMiddleware):
    """Serves private chats and groups, and provides `ctx` and `t` to handlers.

    In groups, only this bot's commands, button presses, and messages from a member
    whose flow is waiting for input get through. Everything else is dropped before it
    touches the database or the logs (002 FR-113). Channels are ignored (FR-117).
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat = _chat_of(event)
        sender = event.from_user
        if chat is None or sender is None:
            return None
        repo: Repository = data["repo"]
        clock = data["clock"]
        bot: Bot = data["bot"]

        if chat.type == "private":
            stored = await repo.get_or_create_chat(chat.id, sender.language_code, clock.now())
            if stored.unreachable_at is not None:
                # A person can only reach the bot if they've unblocked it.
                await repo.set_reachable(stored.id, clock.now())
            data["ctx"] = ChatContext(
                chat=stored,
                member_id=sender.id,
                member_name=display_name(sender.first_name, sender.last_name),
            )
            data["t"] = Translator(stored.language)
            return await handler(event, data)

        if chat.type not in GROUP_TYPES:
            return None

        if isinstance(event, Message) and event.migrate_to_chat_id is not None:
            # The supergroup upgrade needs only the repository.
            return await handler(event, data)

        anonymous = False
        command = None
        if isinstance(event, Message):
            anonymous = event.sender_chat is not None and event.sender_chat.id == chat.id
            command = await command_for_this_bot(event, bot)
            state: FSMContext | None = data.get("state")
            in_flow = state is not None and await state.get_state() is not None
            if command is None and not in_flow:
                return None
        elif isinstance(event, CallbackQuery):
            member, anonymous = await _is_current_member(bot, chat.id, sender.id)
            if not member:
                stored = await repo.get_chat(chat.id)
                t = Translator(stored.language if stored else "en")
                await bot.answer_callback_query(event.id, t("no_longer_available"))
                return None

        stored = await repo.get_or_create_chat(
            chat.id, sender.language_code, clock.now(), kind="group"
        )
        t = Translator(stored.language)
        ctx = ChatContext(
            chat=stored,
            member_id=sender.id,
            member_name=display_name(sender.first_name, sender.last_name),
            thread_id=_thread_of(event),
            is_anonymous_admin=anonymous,
        )
        if anonymous and await self._refuse_anonymous(bot, event, ctx, t, command):
            return None
        data["ctx"] = ctx
        data["t"] = t
        return await handler(event, data)

    @staticmethod
    async def _refuse_anonymous(
        bot: Bot, event: TelegramObject, ctx: ChatContext, t: Translator, command: str | None
    ) -> bool:
        if isinstance(event, Message) and command in _ANONYMOUS_BLOCKED_COMMANDS:
            await bot.send_message(text=t("anonymous_admin"), **ctx.send_kwargs)
            return True
        if isinstance(event, CallbackQuery) and _ANONYMOUS_BLOCKED_BUTTONS.match(event.data or ""):
            await bot.answer_callback_query(event.id, t("anonymous_admin"), show_alert=True)
            return True
        return False


class TimingMiddleware(BaseMiddleware):
    """Logs how long each update took, for the response time goal (SC-007)."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        started = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            kind = event.event_type if isinstance(event, Update) else type(event).__name__
            logger.info("update_handled kind=%s duration_ms=%.0f", kind, elapsed_ms)
