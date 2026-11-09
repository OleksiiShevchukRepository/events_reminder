"""Builds the aiogram dispatcher."""

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from reminder_bot.bot.middleware import ChatContextMiddleware, TimingMiddleware
from reminder_bot.bot.routers import (
    create,
    fallback,
    language,
    membership,
    migration,
    remove,
    start,
    update,
)
from reminder_bot.bot.routers import list as message_list
from reminder_bot.clock import Clock
from reminder_bot.storage.repositories import Repository

ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]


def build_dispatcher(repo: Repository, clock: Clock) -> Dispatcher:
    # Flows live in memory: a restart discards them, as the spec allows for abandoned input.
    dispatcher = Dispatcher(storage=MemoryStorage(), repo=repo, clock=clock)
    dispatcher.update.outer_middleware(TimingMiddleware())
    context = ChatContextMiddleware()
    dispatcher.message.outer_middleware(context)
    dispatcher.callback_query.outer_middleware(context)
    # Order matters: commands first, the catch-all last.
    dispatcher.include_routers(
        start.router,
        migration.router,
        language.router,
        message_list.router,
        remove.router,
        update.router,
        create.router,
        membership.router,
        fallback.router,
    )
    return dispatcher
