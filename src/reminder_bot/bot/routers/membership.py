"""The bot's own membership: blocks in private chats, joining and leaving groups.

Private chats (001 FR-013a): Telegram's docs say this update fires when a user blocks or
unblocks a bot, but don't map the statuses. `kicked` as blocked and `member` as unblocked
is an assumption, logged here so it can be confirmed on a real bot (see quickstart.md).

Groups (002 FR-112, FR-115): a group is reachable while the bot is in it and may post.
Being added, or added back, posts the welcome message.
"""

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatMemberUpdated

from reminder_bot.bot.middleware import GROUP_TYPES
from reminder_bot.clock import Clock
from reminder_bot.i18n import Translator
from reminder_bot.storage.repositories import Repository

logger = logging.getLogger(__name__)

router = Router(name="membership")

_OUTSIDE = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
_CAN_POST = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


def _can_post(member) -> bool:
    if member.status in _CAN_POST:
        return True
    return member.status == ChatMemberStatus.RESTRICTED and bool(
        member.is_member and member.can_send_messages
    )


@router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated, bot: Bot, repo: Repository, clock: Clock
) -> None:
    if event.chat.type == "private":
        await _private(event, repo, clock)
    elif event.chat.type in GROUP_TYPES:
        await _group(event, bot, repo, clock)


async def _private(event: ChatMemberUpdated, repo: Repository, clock: Clock) -> None:
    status = event.new_chat_member.status
    chat_id = event.chat.id
    logger.info("membership_changed chat=%s status=%s", chat_id, status)
    if status == ChatMemberStatus.KICKED:
        await repo.set_unreachable(chat_id, clock.now())
    elif status == ChatMemberStatus.MEMBER:
        await repo.set_reachable(chat_id, clock.now())


async def _group(event: ChatMemberUpdated, bot: Bot, repo: Repository, clock: Clock) -> None:
    chat_id = event.chat.id
    now = clock.now()
    can_post = _can_post(event.new_chat_member)
    logger.info(
        "group_membership_changed chat=%s status=%s can_post=%s",
        chat_id,
        event.new_chat_member.status,
        can_post,
    )
    if not can_post:
        if await repo.get_chat(chat_id) is not None:
            await repo.set_unreachable(chat_id, now)
        return

    # The group's language comes from whoever added the bot (002 FR-111).
    chat = await repo.get_or_create_chat(chat_id, event.from_user.language_code, now, kind="group")
    await repo.set_reachable(chat_id, now)
    if event.old_chat_member.status in _OUTSIDE:
        t = Translator(chat.language)
        try:
            await bot.send_message(chat_id=chat_id, text=t("welcome_group"))
        except TelegramAPIError as error:
            logger.info("welcome_not_sent chat=%s error=%s", chat_id, type(error).__name__)
