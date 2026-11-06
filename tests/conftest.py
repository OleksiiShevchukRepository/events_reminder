"""Shared fixtures: a real temporary database and a fake Telegram."""

from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberBanned,
    ChatMemberMember,
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


class FakeSession(BaseSession):
    """Records every API call and returns what Telegram would, or a queued error."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.errors: deque[Callable[[TelegramMethod[Any]], Exception]] = deque()
        self._next_message_id = 1000

    async def close(self) -> None:
        pass

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: Any = None) -> Any:
        self.calls.append(method)
        if self.errors:
            raise self.errors.popleft()(method)
        if isinstance(method, SendMessage | EditMessageText):
            return self._message_for(method)
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:
        yield b""

    def _message_for(self, method: SendMessage | EditMessageText) -> Message:
        self._next_message_id += 1
        message_id = (
            method.message_id if isinstance(method, EditMessageText) else self._next_message_id
        )
        return Message(
            message_id=message_id,
            date=START,
            chat=Chat(id=method.chat_id, type="private"),
            text=method.text,
            reply_markup=method.reply_markup,
        )

    def sent(self, chat_id: int | None = None) -> list[SendMessage | EditMessageText]:
        return [
            call
            for call in self.calls
            if isinstance(call, SendMessage | EditMessageText)
            and (chat_id is None or call.chat_id == chat_id)
        ]

    def sent_texts(self, chat_id: int | None = None) -> list[str]:
        return [call.text for call in self.sent(chat_id)]


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
            if isinstance(reply.reply_markup, InlineKeyboardMarkup):
                return {
                    button.text: button.callback_data
                    for row in reply.reply_markup.inline_keyboard
                    for button in row
                }
        return {}


class Harness:
    def __init__(self, repo: Repository, clock: FixedClock, session: FakeSession) -> None:
        self.repo = repo
        self.clock = clock
        self.session = session
        self.bot = Bot("123456:TEST", session=session)
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
