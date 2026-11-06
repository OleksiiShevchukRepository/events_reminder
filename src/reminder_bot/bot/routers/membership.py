"""Block and unblock events (FR-013a).

Telegram's docs say this update fires when a private-chat user blocks or unblocks a
bot, but don't map the statuses. `kicked` as blocked and `member` as unblocked is an
assumption, logged here so it can be confirmed on a real bot (see quickstart.md).
"""

import logging

from aiogram import Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated

from reminder_bot.clock import Clock
from reminder_bot.storage.repositories import Repository

logger = logging.getLogger(__name__)

router = Router(name="membership")


@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, repo: Repository, clock: Clock) -> None:
    if event.chat.type != "private":
        return
    status = event.new_chat_member.status
    user_id = event.from_user.id
    logger.info("membership_changed user=%s status=%s", user_id, status)
    if status == ChatMemberStatus.KICKED:
        await repo.set_blocked(user_id, clock.now())
    elif status == ChatMemberStatus.MEMBER:
        await repo.unblock(user_id, clock.now())
