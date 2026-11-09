# Data Model: Group Reminders

Changes to the [001 data model](../001-telegram-reminder-bot/data-model.md). Schedule rules, delivery states and the duplicate-prevention index are unchanged.

## Migration `0002_chats.sql`

One migration, run in a single transaction by the existing migration runner. Existing private data keeps its IDs and meaning.

| Change | Why |
|---|---|
| Rename table `users` to `chats` | Reminders belong to a chat: a private chat or a group (research §1) |
| Rename `chats.blocked_at` to `unreachable_at` | Covers both a blocked private chat and a group the bot can't post in (research §9) |
| Add `chats.kind TEXT NOT NULL DEFAULT 'private' CHECK (kind IN ('private', 'group'))` | Existing rows are private chats |
| Rename `scheduled_messages.user_id` to `chat_id` | Same values; private chat ID equals user ID |
| Add `scheduled_messages.created_by_name TEXT` | Group reminders only (FR-121) |
| Add `scheduled_messages.changed_by_name TEXT` | Group reminders only (FR-121) |
| Recreate `idx_messages_user` as `idx_messages_chat` on `(chat_id, status, next_send_at)` | Follows the renamed column |

SQLite renames columns in place and updates the foreign key from `scheduled_messages` and the existing indexes with them, so no table is rebuilt.

## Entities

### Chat (was User)

| Field | Type | Rules |
|---|---|---|
| `id` | integer | Telegram chat ID. Positive for private chats (equal to the person's ID), negative for groups |
| `kind` | `private` or `group` | Set when the row is created and never changed |
| `language` | `en` or `uk` | Private: from the person's Telegram language. Group: from the member who added the bot or first used it (FR-111) |
| `unreachable_at` | UTC time or empty | Set when the person blocks the bot or the bot can't post in the group. Cleared when reachable again |
| `created_at` | UTC time | |

A group row is created only when the bot is added to the group or a member uses one of its commands there. Ordinary group messages never create or change one (FR-113). Channels never get one (FR-117).

### Reminder (`scheduled_messages`)

All 001 fields stay, with `user_id` renamed `chat_id`. New fields:

| Field | Type | Rules |
|---|---|---|
| `created_by_name` | text or empty | Display name of the member who created it, groups only. Never changes |
| `changed_by_name` | text or empty | Display name of the member who last updated it, groups only. Empty until the first update |

Display name is the member's first name and last name. Anonymous admins can't create or change reminders, so they never need a name (research §8). Private reminders keep both fields empty (FR-123).

### Delivery record

Unchanged. Deliveries follow their reminder through `message_id`, so a supergroup upgrade only changes `chats.id` and `scheduled_messages.chat_id`.

The delivery status `blocked`, and the repository method `record_blocked`, keep their 001 names. For groups they mean the chat was unreachable when sending, not that a person blocked the bot.

## Validation

| Rule | Source |
|---|---|
| At most 100 active reminders per chat, counted in the save transaction | FR-106, 001 FR-020a |
| Every user-facing query filters by the chat the request came from | FR-107, SC-103 |
| In groups, a button press acts only after Telegram confirms the presser is a current member | FR-110a, SC-104 |
| A group flow's input is accepted only from the member who started it | FR-105 |

## State changes

### Chat reachability

```text
reachable --(private: blocked | group: bot removed, kicked, can't post, chat gone)--> unreachable
unreachable --(private: unblocked or writes again | group: bot added back or can post)--> reachable
unreachable for 12 months --> deleted, with its reminders and deliveries
```

Becoming reachable again runs the existing unblock rule: overdue recurring reminders skip ahead with no catch-up, and an overdue one-time reminder is sent once with a note (001 FR-013a).

### Supergroup upgrade

```text
chat(old_id) --(migrate_to_chat_id or TelegramMigrateToChat)--> chat(new_id)
```

One transaction inserts the new chat row with the same language and reachability, points the old chat's reminders at it, and deletes the old row. If the new ID already exists, because both signals arrived, the move does nothing.

### Flow messages (in memory only)

Each create or update flow's state holds two lists of message IDs: the bot's messages and the member's messages. They're deleted when the flow ends and lost on a restart (research §7). Nothing is written to the database.
