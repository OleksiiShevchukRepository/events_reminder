"""Where an update came from: the chat that owns reminders, and the member acting in it."""

from dataclasses import dataclass
from typing import Any

from reminder_bot.storage.repositories import Chat


@dataclass(frozen=True)
class ChatContext:
    chat: Chat
    member_id: int
    member_name: str
    # The topic the member is working in. Replies go there; reminders don't (002 FR-114).
    thread_id: int | None = None
    # An admin posting as the group itself, who can't be told apart from other admins.
    is_anonymous_admin: bool = False

    @property
    def chat_id(self) -> int:
        return self.chat.id

    @property
    def is_group(self) -> bool:
        return self.chat.is_group

    @property
    def send_kwargs(self) -> dict[str, Any]:
        """Arguments that send a reply to where the member is working."""
        if self.thread_id is None:
            return {"chat_id": self.chat.id}
        return {"chat_id": self.chat.id, "message_thread_id": self.thread_id}

    @property
    def creator_name(self) -> str | None:
        """The name stored with a reminder: groups only (002 FR-123)."""
        return self.member_name if self.is_group else None


def display_name(first_name: str, last_name: str | None) -> str:
    return f"{first_name} {last_name}".strip() if last_name else first_name
