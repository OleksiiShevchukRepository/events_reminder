"""A group upgraded to a supergroup gets a new ID (002 FR-116).

Telegram posts a service message with the new ID in the old group. The scheduler can
also learn of it first from a failed send; either way the move happens once.
"""

import logging

from aiogram import F, Router
from aiogram.types import Message

from reminder_bot.storage.repositories import Repository

logger = logging.getLogger(__name__)

router = Router(name="migration")


@router.message(F.migrate_to_chat_id)
async def on_migrate(message: Message, repo: Repository) -> None:
    moved = await repo.move_chat(message.chat.id, message.migrate_to_chat_id)
    logger.info(
        "group_upgraded old=%s new=%s moved=%s",
        message.chat.id,
        message.migrate_to_chat_id,
        moved,
    )
