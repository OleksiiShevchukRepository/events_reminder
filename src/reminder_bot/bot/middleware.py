"""Runs before handlers: private chats only, and who is asking."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update

from reminder_bot.i18n import Translator

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


def _chat_of(event: TelegramObject) -> Chat | None:
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat
    return None


class UserContextMiddleware(BaseMiddleware):
    """Ignores anything outside private chats and provides `user` and `t` to handlers."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat = _chat_of(event)
        sender = event.from_user
        if chat is None or chat.type != "private" or sender is None:
            return None

        repo, clock = data["repo"], data["clock"]
        user = await repo.get_or_create_user(sender.id, sender.language_code, clock.now())
        if user.blocked_at is not None:
            # A user can only reach the bot if they've unblocked it.
            await repo.unblock(user.id, clock.now())
        data["user"] = user
        data["t"] = Translator(user.language)
        return await handler(event, data)


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
