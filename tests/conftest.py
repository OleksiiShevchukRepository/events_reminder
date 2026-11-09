"""Shared fixtures: a real temporary database and a fake Telegram."""

from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramMigrateToChat
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessages,
    EditMessageText,
    GetChatMember,
    GetMe,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberAdministrator,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberRestricted,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    Update,
)
from aiogram.types import User as TelegramUser

from reminder_bot.bot.app import build_dispatcher
from reminder_bot.clock import FixedClock
from reminder_bot.storage.db import Database
from reminder_bot.storage.repositories import Repository

# 14:00 on 6 November 2026 in Kyiv.
START = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
USER = 1001
OTHER_USER = 2002
GROUP = -1001234
OTHER_GROUP = -1005678
BOT_ID = 123456
BOT_USERNAME = "reminder_test_bot"
BOT_USER = TelegramUser(id=BOT_ID, is_bot=True, first_name="Reminder", username=BOT_USERNAME)
# The account Telegram shows as the sender of an anonymous admin's messages.
ANONYMOUS_ADMIN_BOT = TelegramUser(id=1087968824, is_bot=True, first_name="Group")


def _with_flags(model: Any, **values: Any) -> Any:
    """Build a chat member type, setting every required permission flag not given to False."""
    for name, field in model.model_fields.items():
        if field.is_required() and name not in values and field.annotation is bool:
            values[name] = False
    return model(**values)


def administrator(user: TelegramUser, anonymous: bool = False) -> ChatMemberAdministrator:
    return _with_flags(
        ChatMemberAdministrator,
        user=user,
        is_anonymous=anonymous,
        can_manage_chat=True,
        can_delete_messages=True,
    )


def restricted(user: TelegramUser, can_send_messages: bool) -> ChatMemberRestricted:
    return _with_flags(
        ChatMemberRestricted,
        user=user,
        is_member=True,
        can_send_messages=can_send_messages,
        until_date=START,
    )


class FakeSession(BaseSession):
    """Records every API call and returns what Telegram would, or a queued error."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.errors: deque[Callable[[TelegramMethod[Any]], Exception]] = deque()
        self._next_message_id = 1000
        # Telegram's answer to getChatMember, by user ID. Anyone not listed is a member.
        self.member_status: dict[int, str] = {}
        # When False, deleteMessages fails if it includes messages the bot didn't send.
        self.can_delete_members_messages = True
        self.bot_message_ids: set[int] = set()

    async def close(self) -> None:
        pass

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: Any = None) -> Any:
        self.calls.append(method)
        if self.errors:
            raise self.errors.popleft()(method)
        if isinstance(method, SendMessage | EditMessageText):
            return self._message_for(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, GetChatMember):
            return self._member(method.user_id)
        if isinstance(method, DeleteMessages):
            theirs = set(method.message_ids) - self.bot_message_ids
            if theirs and not self.can_delete_members_messages:
                raise TelegramBadRequest(method, "Bad Request: message can't be deleted")
        return True

    def _member(self, user_id: int) -> Any:
        user = TelegramUser(id=user_id, is_bot=False, first_name="Member")
        status = self.member_status.get(user_id, "member")
        if status == "anonymous":
            return administrator(user, anonymous=True)
        if status == "administrator":
            return administrator(user)
        if status == "left":
            return ChatMemberLeft(user=user)
        if status == "kicked":
            return ChatMemberBanned(user=user, until_date=START)
        return ChatMemberMember(user=user)

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:
        yield b""

    def _message_for(self, method: SendMessage | EditMessageText) -> Message:
        self._next_message_id += 1
        message_id = (
            method.message_id if isinstance(method, EditMessageText) else self._next_message_id
        )
        self.bot_message_ids.add(message_id)
        markup = method.reply_markup
        return Message(
            message_id=message_id,
            date=START,
            chat=Chat(id=method.chat_id, type="private" if method.chat_id > 0 else "supergroup"),
            text=method.text,
            reply_markup=markup if isinstance(markup, InlineKeyboardMarkup) else None,
        )

    def deleted(self, chat_id: int | None = None) -> list[DeleteMessages]:
        return [
            call
            for call in self.calls
            if isinstance(call, DeleteMessages) and (chat_id is None or call.chat_id == chat_id)
        ]

    def deleted_ids(self, chat_id: int | None = None) -> set[int]:
        return {message_id for call in self.deleted(chat_id) for message_id in call.message_ids}

    def callback_answers(self) -> list[str | None]:
        return [call.text for call in self.calls if isinstance(call, AnswerCallbackQuery)]

    def sent(self, chat_id: int | None = None) -> list[SendMessage | EditMessageText]:
        return [
            call
            for call in self.calls
            if isinstance(call, SendMessage | EditMessageText)
            and (chat_id is None or call.chat_id == chat_id)
        ]

    def sent_texts(self, chat_id: int | None = None) -> list[str]:
        return [call.text for call in self.sent(chat_id)]


def _buttons(markup: Any) -> dict[str, str]:
    if not isinstance(markup, InlineKeyboardMarkup):
        return {}
    return {button.text: button.callback_data for row in markup.inline_keyboard for button in row}


class FakeChat:
    """Plays one Telegram user talking to the bot through the real dispatcher."""

    def __init__(self, harness: Harness, user_id: int, language: str | None) -> None:
        self.harness = harness
        self.user_id = user_id
        self.language = language

    @property
    def _user(self) -> TelegramUser:
        return TelegramUser(
            id=self.user_id, is_bot=False, first_name="Test", language_code=self.language
        )

    def _chat(self, chat_type: str = "private") -> Chat:
        return Chat(id=self.user_id, type=chat_type)

    async def send(self, text: str, chat_type: str = "private") -> None:
        await self.harness.feed(
            message=Message(
                message_id=self.harness.next_id(),
                date=START,
                chat=self._chat(chat_type),
                from_user=self._user,
                text=text,
            )
        )

    async def send_photo(self) -> None:
        await self.harness.feed(
            message=Message(
                message_id=self.harness.next_id(),
                date=START,
                chat=self._chat(),
                from_user=self._user,
                photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)],
            )
        )

    async def press(self, data: str) -> None:
        await self.harness.feed(
            callback_query=CallbackQuery(
                id=str(self.harness.next_id()),
                from_user=self._user,
                chat_instance="test",
                data=data,
                message=Message(message_id=self.harness.next_id(), date=START, chat=self._chat()),
            )
        )

    async def set_status(self, status: str) -> None:
        member = (
            ChatMemberBanned(user=self._user, until_date=START)
            if status == "kicked"
            else ChatMemberMember(user=self._user)
        )
        old = ChatMemberMember(user=self._user) if status == "kicked" else member
        await self.harness.feed(
            my_chat_member=ChatMemberUpdated(
                chat=self._chat(),
                from_user=self._user,
                date=START,
                old_chat_member=old,
                new_chat_member=member,
            )
        )

    # What the user sees

    def replies(self) -> list[SendMessage | EditMessageText]:
        return self.harness.session.sent(self.user_id)

    def texts(self) -> list[str]:
        return [reply.text for reply in self.replies()]

    @property
    def last_text(self) -> str:
        return self.texts()[-1]

    def last_buttons(self) -> dict[str, str]:
        """Label to callback data for the latest message that has buttons."""
        for reply in reversed(self.replies()):
            buttons = _buttons(reply.reply_markup)
            if buttons:
                return buttons
        return {}


class FakeGroup:
    """Plays a group chat with several members, all talking through the real dispatcher."""

    def __init__(self, harness: Harness, chat_id: int, title: str, forum: bool) -> None:
        self.harness = harness
        self.chat_id = chat_id
        self.title = title
        self.forum = forum

    @staticmethod
    def member(
        user_id: int, first_name: str, last_name: str | None = None, language: str | None = "en"
    ) -> TelegramUser:
        return TelegramUser(
            id=user_id,
            is_bot=False,
            first_name=first_name,
            last_name=last_name,
            language_code=language,
        )

    @property
    def _chat(self) -> Chat:
        return Chat(
            id=self.chat_id, type="supergroup", title=self.title, is_forum=self.forum or None
        )

    @staticmethod
    def _topic(thread_id: int | None) -> dict[str, Any]:
        if thread_id is None:
            return {}
        return {"message_thread_id": thread_id, "is_topic_message": True}

    async def send(
        self,
        text: str,
        member: TelegramUser,
        reply_to: int | None = None,
        thread_id: int | None = None,
        anonymous: bool = False,
    ) -> int:
        """Send a message as a member. `reply_to` is the ID of a bot message being replied to."""
        message_id = self.harness.next_id()
        reply = None
        if reply_to is not None:
            reply = Message(message_id=reply_to, date=START, chat=self._chat, from_user=BOT_USER)
        await self.harness.feed(
            message=Message(
                message_id=message_id,
                date=START,
                chat=self._chat,
                from_user=ANONYMOUS_ADMIN_BOT if anonymous else member,
                sender_chat=self._chat if anonymous else None,
                text=text,
                reply_to_message=reply,
                **self._topic(thread_id),
            )
        )
        return message_id

    async def answer(self, text: str, member: TelegramUser, thread_id: int | None = None) -> int:
        """Reply to the bot's latest message, as a member using the reply box would."""
        latest = max(self.harness.session.bot_message_ids)
        return await self.send(text, member, reply_to=latest, thread_id=thread_id)

    async def press(self, data: str, member: TelegramUser, thread_id: int | None = None) -> None:
        await self.harness.feed(
            callback_query=CallbackQuery(
                id=str(self.harness.next_id()),
                from_user=member,
                chat_instance="group",
                data=data,
                message=Message(
                    message_id=self.harness.next_id(),
                    date=START,
                    chat=self._chat,
                    **self._topic(thread_id),
                ),
            )
        )

    async def bot_status(
        self, old: str, new: str, by: TelegramUser, can_send_messages: bool = True
    ) -> None:
        """The bot's own membership changes, as reported by `my_chat_member`."""

        def status(name: str) -> Any:
            if name == "left":
                return ChatMemberLeft(user=BOT_USER)
            if name == "kicked":
                return ChatMemberBanned(user=BOT_USER, until_date=START)
            if name == "restricted":
                return restricted(BOT_USER, can_send_messages)
            if name == "administrator":
                return administrator(BOT_USER)
            return ChatMemberMember(user=BOT_USER)

        await self.harness.feed(
            my_chat_member=ChatMemberUpdated(
                chat=self._chat,
                from_user=by,
                date=START,
                old_chat_member=status(old),
                new_chat_member=status(new),
            )
        )

    async def migrate(self, new_chat_id: int, by: TelegramUser) -> None:
        """Telegram's service message in the old group when it becomes a supergroup."""
        await self.harness.feed(
            message=Message(
                message_id=self.harness.next_id(),
                date=START,
                chat=Chat(id=self.chat_id, type="group", title=self.title),
                from_user=by,
                migrate_to_chat_id=new_chat_id,
            )
        )

    # What the group sees

    def replies(self) -> list[SendMessage | EditMessageText]:
        return self.harness.session.sent(self.chat_id)

    def texts(self) -> list[str]:
        return [reply.text for reply in self.replies()]

    @property
    def last_reply(self) -> SendMessage | EditMessageText:
        return self.replies()[-1]

    @property
    def last_text(self) -> str:
        return self.texts()[-1]

    def last_buttons(self) -> dict[str, str]:
        for reply in reversed(self.replies()):
            buttons = _buttons(reply.reply_markup)
            if buttons:
                return buttons
        return {}


def forbidden(method: TelegramMethod[Any]) -> Exception:
    return TelegramForbiddenError(method, "Forbidden: bot was kicked from the group chat")


def cannot_post(method: TelegramMethod[Any]) -> Exception:
    return TelegramBadRequest(
        method, "Bad Request: not enough rights to send text messages to the chat"
    )


def chat_gone(method: TelegramMethod[Any]) -> Exception:
    return TelegramBadRequest(method, "Bad Request: chat not found")


def upgraded_to(new_chat_id: int) -> Callable[[TelegramMethod[Any]], Exception]:
    def error(method: TelegramMethod[Any]) -> Exception:
        return TelegramMigrateToChat(
            method,
            "Bad Request: group chat was upgraded to a supergroup chat",
            migrate_to_chat_id=new_chat_id,
        )

    return error


class Harness:
    def __init__(self, repo: Repository, clock: FixedClock, session: FakeSession) -> None:
        self.repo = repo
        self.clock = clock
        self.session = session
        self.bot = Bot(f"{BOT_ID}:TEST", session=session)
        self.dispatcher: Dispatcher = build_dispatcher(repo, clock)
        self._next_id = 0

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def feed(self, **update: Any) -> None:
        # Exceptions surface in tests instead of being logged and swallowed.
        await self.dispatcher.feed_update(self.bot, Update(update_id=self.next_id(), **update))

    def chat(self, user_id: int = USER, language: str | None = "en") -> FakeChat:
        return FakeChat(self, user_id, language)

    def group(self, chat_id: int = GROUP, title: str = "Family", forum: bool = False) -> FakeGroup:
        return FakeGroup(self, chat_id, title, forum)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(START)


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = await Database.open(tmp_path / "test.db")
    await database.migrate()
    yield database
    await database.close()


@pytest.fixture
def repo(db: Database) -> Repository:
    return Repository(db)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def harness(repo: Repository, clock: FixedClock, session: FakeSession) -> Iterator[Harness]:
    instance = Harness(repo, clock, session)
    yield instance
    # Routers are module-level and aiogram allows one parent at a time, so each test
    # releases them for the next test's dispatcher. Production builds only one.
    for router in instance.dispatcher.sub_routers:
        router._parent_router = None


@pytest.fixture
def chat(harness: Harness) -> FakeChat:
    return harness.chat()
