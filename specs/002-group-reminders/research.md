# Research: Group Reminders

Decisions for adding groups to the existing bot. The stack, delivery rules and schedule rules from [001 research.md](../001-telegram-reminder-bot/research.md) stay as they are.

## 1. One owner for reminders: the chat

**Decision**: Reminders belong to a **chat**, not a user. Telegram gives a private chat the same ID as the person, and gives groups negative IDs, so one `chats` table holds both. The `users` table becomes `chats`, and `scheduled_messages.user_id` becomes `chat_id`, in a numbered migration. A `kind` column says `private` or `group`.

**Rationale**: Almost every rule (limit of 100, language, pausing when unreachable, 12-month deletion, listing and scoping every query) already works per owner. Making the owner a chat gives groups all of it with no second code path, and existing rows keep their IDs, so no data moves.

**Alternatives considered**:
- A separate `groups` table and a nullable `group_id` on reminders: every query would need "user or group" logic, and the risk of a scoping mistake (SC-103) grows.
- Storing groups in `users` without renaming: works, but the names would mislead every future reader.

## 2. Context passed to handlers

**Decision**: The middleware gives handlers a `ChatContext` in place of `user`: the chat (ID, kind, language), the topic the member is working in, and the member (ID and display name). Handlers send to `ctx.chat_id` in `ctx.thread_id`, and the translator follows the chat's language.

**Rationale**: Handlers today send to `user.id`, which is only correct in private chats. One object makes "reply where the member is working" the default (FR-114) and keeps the member separate from the owner.

## 3. Who can see what in a group

**Decision**: Every query stays scoped by owner, now the chat ID. A button can only act on reminders of the chat its message is in. For button presses in groups, the bot also checks with Telegram that the presser is a current member (`getChatMember`) before showing or changing anything (FR-110a).

**Rationale**: Scoping by the button's chat already stops one group touching another (SC-103). The membership check covers public groups, where people who aren't members can read history and press old buttons (SC-104). It costs one Telegram call per group button press, which fits the 2-second response goal.

**Alternatives considered**: Caching membership. Not needed at this scale, and a cache could let someone act shortly after leaving.

## 4. Answering questions in a group

**Decision**:
- Each question in a group is sent with Telegram's reply prompt (`ForceReply`, `selective`) and starts with a mention of the member, so the reply box opens only for them (FR-104). The mention is a text mention entity, which works for members without a username and needs no parse mode.
- The flow is keyed by member and chat (aiogram's default `USER_IN_CHAT`), so two members' flows never mix (FR-105).
- A group message is taken as an answer only if it comes from a member whose flow is waiting for input. In a group where the bot isn't an admin, Telegram only delivers commands and replies to the bot, so that member must reply. Where the bot is an admin, Telegram delivers all messages, so the same rule lets that member type without replying (FR-104a) with no extra code.

- Telegram allows only one kind of reply markup per message, so a question with the reply prompt can't also have the inline Cancel button. Group questions that need a typed answer end with the translated hint "Send /cancel to stop" instead. Questions answered with buttons keep the Cancel button, as in private chats.

**Rationale**: This works with Telegram's default privacy mode, so groups change nothing. The member filter alone gives both behaviors the spec asks for.

**To confirm on a real bot**: that a selective reply prompt with a text mention opens the reply box only for that member, including after a button press, when there is no member message to reply to.

## 5. Not storing ordinary group chat

**Decision**: In groups, the middleware drops any message that is neither one of the bot's own commands nor an answer from a member with an active flow, before it reads or writes the database (FR-113). Nothing about a group is stored until the bot joins it or a member uses a command. Logs record only update kinds, as now. The catch-all "I didn't understand" reply is for private chats only.

**Rationale**: As an admin, the bot receives every group message. They must not touch storage or logs.

## 6. Topics

**Decision**: Questions and replies use the `message_thread_id` of the topic where the member is working. Delivered reminders are sent without a thread ID, which Telegram puts in the General topic (FR-114). The topic isn't stored with the reminder.

## 7. Flow clean-up

**Decision**: Each flow keeps the IDs of the messages it produced in its in-memory state, separated into the bot's messages and the member's. This includes the starting command, every question, every error reply and every answer. One `end_flow` helper replaces all direct `state.clear()` calls. It deletes the tracked messages, then clears the state. The final message (confirmation, "Cancelled" or the next command's reply) is sent after deletion and isn't tracked.

- The bot's messages are deleted with one `deleteMessages` call, and the member's with a second. Each call is allowed to fail on its own, so a group without admin rights still loses the bot's questions (FR-120), and a failure never stops the save or cancel.
- In private chats Telegram lets bots delete both sides, so clean-up always works there.
- Messages older than 48 hours, and flows lost on a restart, aren't cleaned up, as the spec allows.

**Rationale**: Tracking in the flow state needs no new storage, and a flow lost on restart has nothing left to clean anyway. One helper makes it impossible to end a flow without cleaning up.

**Alternatives considered**: Storing message IDs in the database to clean up after restarts. The spec accepts leftovers in that case, and it would add writes to every step.

## 8. Names for "who did what"

**Decision**: Group reminders store `created_by_name` and `changed_by_name`: the member's display name (first and last name) at the moment of the action (FR-123). No user ID is stored. Private reminders leave both empty. Anonymous group admins can't start flows: Telegram reports their messages as coming from the group but their button presses from their real account, so a flow can't be linked to one person. When one sends `/new`, `/language` or presses Edit or Remove, the bot asks them to turn off "Remain anonymous" and starts nothing. `/list` and `/help` still work.

**Rationale**: The spec asks for names at the time of the action, so no lookup or member table is needed. Storing only a name keeps member data to a minimum.

## 9. Joining, leaving and losing the right to post

**Decision**: Group reachability is handled like a blocked private chat, using the existing `blocked_at` field, renamed `unreachable_at`.
- The bot's own `my_chat_member` update with `member` or `administrator` status, or `restricted` with the right to send messages, makes the group reachable. If the group is new, the bot stores it with the language of the member who added it and posts the welcome message (FR-111, FR-112).
- `left`, `kicked`, or `restricted` without the right to send makes it unreachable.
- When sending, `403` errors, and `400` errors meaning the chat is gone or the bot can't send there, mark the group unreachable, the same as a block. Coming back follows the 001 unblock rules: recurring reminders skip ahead and one-time reminders are sent once with a note.

**Rationale**: The spec's group rules match the existing block rules exactly, so they share code and tests.

## 10. Supergroup upgrade

**Decision**: When the old group's chat receives a service message with `migrate_to_chat_id`, the bot moves the chat row, reminders and delivery records to the new ID in one transaction. If the scheduler gets `TelegramMigrateToChat` first, it moves the chat the same way and saves the send as `retrying` for the new ID, so it is neither lost nor sent twice (FR-116).

**Rationale**: Telegram reports the upgrade both ways, and either can arrive first.

## 11. Sending speed in groups

**Decision**: The rate limiter spaces sends to each group 3 seconds apart, inside Telegram's limit of about 20 messages a minute per group. Private chats keep 1 second. The bot's replies in the group count towards the same limit, so the target is 15 reminders due together, which finish within about 42 seconds (SC-102). More are still all sent; a 429 response is retried as in 001.

## 12. Commands in groups

**Decision**: Commands are registered for private chats and for all group chats. In groups, the bot reacts to `/new`, `/list`, `/language`, `/help`, `/cancel` and `/start`, including the `/new@BotName` form, and ignores commands meant for other bots. aiogram's `Command` filter already checks the bot name.

## 13. Channels

**Decision**: The middleware and the membership handler ignore channels entirely (FR-117).

## 14. Testing

**Decision**: The fake Telegram session in `tests/conftest.py` gains group chats with negative IDs, several members, topics, replies, `deleteMessages` and `getChatMember` results, and errors for an unreachable group and an upgrade. All 001 tests must pass with only the flow clean-up added (SC-106).
