---

description: "Task list for Group Reminders"
---

# Tasks: Group Reminders

**Input**: Design documents from `specs/002-group-reminders/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/bot-interface.md](contracts/bot-interface.md), [quickstart.md](quickstart.md)

**Tests**: Included, as in 001. Isolation between chats (SC-103, SC-104), member-only flows (SC-105) and the unchanged private behavior (SC-106) can only be proven reliably by automated tests. Write each test first and confirm it fails before implementing.

**Organization**: Tasks are grouped by user story. US1 works on its own after the foundation. US3 selects reminders from the list built in US2. The lifecycle phase covers the edge cases shared by all stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: The user story the task belongs to

All paths are relative to the repository root. "The 001 rules" means the behavior in `specs/001-telegram-reminder-bot/`.

---

## Phase 1: Setup (Test Harness)

**Purpose**: Let tests drive group chats before any code changes

- [X] T001 Extend `tests/conftest.py` so the fake Telegram session and chats support groups: a `harness.group(chat_id=-100…, title=…, language=…)` helper returning a `FakeGroup` with several members (each with first and last name), `send(text, member, reply_to=None, thread_id=None)`, `press(data, member)`, service updates for the bot being added, removed and restricted (`my_chat_member` with `member`, `administrator`, `left`, `kicked`, `restricted`), a `migrate_to_chat_id` service message, and recorded `deleteMessages` and `getChatMember` calls with settable results (deletion allowed or refused, member or `left`). Every sent message gets a unique `message_id`, and `reply_markup`, `message_thread_id` and `entities` are kept for assertions
- [X] T002 Add fake error responses in `tests/conftest.py` for group sends: `403 bot was kicked from the group chat`, `400 not enough rights to send text messages to the chat`, `400 chat not found`, and `400 group chat was upgraded to a supergroup chat` with `migrate_to_chat_id`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reminders owned by chats, a chat context for handlers, and the shared flow helpers

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Storage: from user to chat

- [X] T003 Write `tests/integration/test_migration_0002.py`: a database created with only `0001_initial.sql` and filled with a user, active and completed messages and deliveries, then migrated, keeps every row with the same IDs, has `chats.kind = 'private'`, `unreachable_at` equal to the old `blocked_at`, `scheduled_messages.chat_id` equal to the old `user_id`, empty `created_by_name` and `changed_by_name`, a working foreign key cascade from `chats`, and the `idx_messages_chat` index
- [X] T004 Create `src/reminder_bot/storage/migrations/0002_chats.sql` as described in data-model.md: rename `users` to `chats`, `blocked_at` to `unreachable_at`, `scheduled_messages.user_id` to `chat_id`, add `chats.kind` with default `'private'` and its check, add `created_by_name` and `changed_by_name`, and replace `idx_messages_user` with `idx_messages_chat (chat_id, status, next_send_at)`
- [X] T005 Rename the user concept to chat in `src/reminder_bot/storage/repositories.py`: `User` becomes `Chat` with `id`, `kind`, `language`, `unreachable_at`; `get_or_create_user` becomes `get_or_create_chat(chat_id, kind, telegram_language, now)`; `set_blocked`, `unblock`, `delete_users_blocked_before` become `set_unreachable`, `set_reachable`, `delete_chats_unreachable_before`; every `user_id` parameter, query and dataclass field (`Message`, `Claim`, `DueMessage`, `DueRetry`) becomes `chat_id`; `Message` gains `created_by_name` and `changed_by_name`; `create_message` takes an optional `created_by_name`, and `update_text` and `update_schedule` take an optional `changed_by_name` that they store. Keep the module docstring's scoping rule, now "scoped to the chat that asked"
- [X] T006 Update every caller of the renamed repository API in `src/reminder_bot/bot/middleware.py`, `src/reminder_bot/bot/routers/*.py`, `src/reminder_bot/bot/views.py`, `src/reminder_bot/scheduler/dispatcher.py` and `src/reminder_bot/scheduler/maintenance.py`, with private chats behaving exactly as before
- [X] T007 Update the existing tests in `tests/` for the renamed API only (no behavior changes), then run `uv run pytest` and confirm every 001 test passes (SC-106)

### Chat context and group routing

- [X] T008 Create `src/reminder_bot/bot/context.py` with a frozen `ChatContext`: `chat` (the stored `Chat`), `thread_id` (topic of the incoming update, or None), `member_id`, `member_name` (first and last name), `is_anonymous_admin` (true when the message was sent as the group itself), and properties `chat_id`, `is_group`, and `send_kwargs` returning `chat_id` plus `message_thread_id` when set
- [X] T009 Write `tests/contract/test_group_routing.py`: ordinary group messages, other bots' commands and unknown commands get no reply and create no `chats` row; a known command such as `/help` and `/help@<bot username>` in a group creates a `group` chat row and replies in the same topic; channel posts and channel `my_chat_member` updates store nothing (FR-113, FR-117); private behavior is unchanged
- [X] T010 Rework `src/reminder_bot/bot/middleware.py` (`UserContextMiddleware` becomes `ChatContextMiddleware`): ignore channels; in groups and supergroups, pass on only the bot's known commands, callback queries, and messages from a member whose FSM state is set (use `data["state"]`), dropping everything else before any database access; load or create the chat with the right `kind` (a private chat that writes again is set reachable, as now); when an anonymous admin sends `/new` or `/language`, or presses Edit or Remove, reply with `anonymous_admin` and stop, while `/list` and `/help` still work; provide `ctx` and a `Translator` in the chat's language. Do not log message text
- [X] T011 Replace `user: User` with `ctx: ChatContext` in every handler in `src/reminder_bot/bot/routers/`, sending with `**ctx.send_kwargs` instead of `user.id`, and make `src/reminder_bot/bot/routers/fallback.py` reply to unknown input only in private chats
- [X] T012 [P] Register commands for `BotCommandScopeAllGroupChats` in both languages in `src/reminder_bot/__main__.py`, alongside the existing private scope

### Flow helpers

- [X] T013 Create `src/reminder_bot/bot/flow.py` with: `track_member(state, message_id)` and `track_bot(state, message_id)`, which append to the flow's `member_messages` and `bot_messages` lists in FSM data; `ask(bot, state, ctx, t, key, reply_markup=None, **params)`, which sends a question with `ctx.send_kwargs`, records its ID, and in groups starts the text with the member's name as a `text_mention` entity; for typed-answer questions in groups it attaches `ForceReply(selective=True)` and appends the `cancel_hint` text in place of the Cancel button, because Telegram can't combine the two; and `end_flow(bot, state, ctx)`, which deletes the tracked bot messages and member messages with two separate `deleteMessages` calls, each ignoring Telegram errors, then clears the state. Flows that use inline buttons (recurrence choice) send the mention without `ForceReply`

**Checkpoint**: All 001 tests pass, groups are recognized but ignored except for commands, and the flow helpers exist.

---

## Phase 3: User Story 1 - Create a group reminder and receive it in the group (Priority: P1) 🎯 MVP

**Goal**: A member creates a reminder in a group with the guided steps, and the bot posts it there on time. Flows clean up after themselves in groups and private chats.

**Independent Test**: In a test group, create a one-time reminder a few minutes ahead and check it appears in the group, and not in anyone's private chat.

### Tests for User Story 1

- [X] T014 [P] [US1] Write `tests/contract/test_group_create.py`: the full create flow in a group for each recurrence type saves a reminder owned by the group with `created_by_name`; each question mentions the member and carries a selective `ForceReply` (or the recurrence buttons); group text questions show the `/cancel` hint and no inline Cancel button, while the recurrence question keeps its Cancel button; an anonymous admin's `/new` gets the `anonymous_admin` reply and starts nothing; a reply from the member is accepted; a message from another member, and another member's press of the flow's buttons, change nothing and the press gets a "This isn't your request" callback answer; two members' interleaved flows save two separate reminders with the right texts (SC-105); the group limit of 100 is separate from members' private limits (FR-106); Cancel saves nothing; the confirmation reads "Saved by <name>."; questions and confirmation carry the topic's `message_thread_id`
- [X] T015 [P] [US1] Write `tests/contract/test_flow_cleanup.py`: after a group create ends by save, Cancel, `/cancel` or another command, `deleteMessages` is called once with the bot's questions and error replies and once with the member's command and answers, and the final message isn't included; when the member deletion fails, the bot deletion still happens and the reminder is still saved (FR-120); in a private chat the same flow deletes both sides and leaves only the confirmation or "Cancelled" (FR-119); update flows clean up the same way
- [X] T016 [P] [US1] Write group cases in `tests/integration/test_dispatcher.py`: a due group reminder is sent to the group's ID with no `message_thread_id` (General topic, FR-114) and no names; overdue group reminders get the note; the rate limiter spaces sends to one group at least 3 seconds apart and private chats 1 second (research §11), so 15 due together finish within about 45 seconds of fake time, and 25 due together are all sent

### Implementation for User Story 1

- [X] T017 [US1] Use `flow.ask()` for every question and error reply in `src/reminder_bot/bot/routers/create.py`, record the member's command and each answer with `flow.track_member()`, and pass `ctx.member_name` as `created_by_name` for group chats only
- [X] T018 [US1] Replace every direct `state.clear()` that ends a create or update flow with `flow.end_flow()` in `src/reminder_bot/bot/routers/start.py`, `create.py`, `update.py`, `remove.py`, `list.py`, `language.py` and `fallback.py`, so saving, Cancel, `/cancel` and any other command all clean up, with the final message sent after the deletion
- [X] T019 [US1] Make a flow's buttons answer only the member who started it: in `src/reminder_bot/bot/routers/fallback.py`, a group button press that matches a flow callback (`rec:*`, `flow:cancel`) from a member without that flow state gets `answer_callback_query(text=t("not_your_request"))` and nothing else
- [X] T020 [US1] Add group confirmations in `src/reminder_bot/bot/views.py` and `create.py`: `saved_by` ("Saved by {name}.") replaces `saved` in groups
- [X] T021 [P] [US1] Add group spacing to `RateLimiter` in `src/reminder_bot/scheduler/dispatcher.py`: `GROUP_SPACING = timedelta(seconds=3)` for negative chat IDs, `PER_CHAT_SPACING` unchanged for private chats; sends keep using the chat ID with no thread, so they land in General
- [X] T022 [P] [US1] Add the US1 text to `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`: `saved_by`, `not_your_request`, `anonymous_admin`, `cancel_hint` ("Send /cancel to stop."), the "please reply to this message" wording for group questions (for example `ask_mention` "{name}, {question}" and a short `reply_hint`), keeping keys and placeholders identical

**Checkpoint**: Group reminders can be created and are delivered to the group; flows clean up in groups and private chats.

---

## Phase 4: User Story 2 - See a group's reminders (Priority: P2)

**Goal**: `/list` in a group shows only that group's reminders, and only current members can use the list's buttons.

**Independent Test**: Create group and private reminders, then check `/list` in the group and in a private chat each shows only its own.

### Tests for User Story 2

- [X] T023 [P] [US2] Write `tests/contract/test_group_list.py`: `/list` in a group shows only that group's reminders with paging of 10; the same member's private `/list` shows only private reminders; two groups never see each other's reminders, including when a button's callback data names another chat's reminder ID (SC-103); a button press from someone `getChatMember` reports as `left` or `kicked` gets "This is no longer available" and changes nothing (SC-104); an empty group list offers New reminder; a group reminder's screen shows "Created by: <name>"

### Implementation for User Story 2

- [X] T024 [US2] Add the membership check to `ChatContextMiddleware` in `src/reminder_bot/bot/middleware.py`: for callback queries in groups, call `getChatMember` and stop with `answer_callback_query(text=t("no_longer_available"))` unless the status is `creator`, `administrator`, `member`, or `restricted` with `is_member`; treat a failed check as not a member
- [X] T025 [US2] Scope `src/reminder_bot/bot/routers/list.py` to `ctx.chat_id` for listing, paging and opening, and add the "Created by" and, when set, "Last changed by" lines to the reminder screen in `src/reminder_bot/bot/views.py` for group reminders only (FR-121)
- [X] T026 [P] [US2] Add `created_by` and `changed_by` text to `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`

**Checkpoint**: Groups can list and open their reminders, and nobody outside a group can.

---

## Phase 5: User Story 3 - Change or remove a group's reminders (Priority: P3)

**Goal**: Any member updates or removes any group reminder, and the group sees who did it.

**Independent Test**: From one member create a group reminder; from a second member change its time and remove another; check the list and the named confirmations.

### Tests for User Story 3

- [X] T027 [P] [US3] Write `tests/contract/test_group_update_remove.py`: a second member can edit text, recurrence, date and time of the first member's reminder, and the next send uses the new values; `changed_by_name` is saved and shown on the screen; the confirmation reads "Updated by <name>."; a second member can remove it, and the remaining message reads "Removed by <name>:" with the text; it is never sent afterwards; edit flows in groups mention the member, accept only that member, and clean up like create flows

### Implementation for User Story 3

- [X] T028 [US3] Use `flow.ask()`, `flow.track_member()` and `flow.end_flow()` throughout `src/reminder_bot/bot/routers/update.py`, pass `ctx.member_name` as `changed_by_name` for groups, and use `updated_by` in group confirmations
- [X] T029 [US3] Use `removed_by` with the removed text for group removals in `src/reminder_bot/bot/routers/remove.py`, keeping the 001 wording in private chats
- [X] T030 [P] [US3] Add `updated_by` and `removed_by` text to `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`

**Checkpoint**: Group reminders can be fully managed by any member, with names shown.

---

## Phase 6: User Story 4 - Group language (Priority: P3)

**Goal**: Each group has one bot language, which any member can change.

**Independent Test**: Add the bot from a Ukrainian account and check it replies in Ukrainian, then switch to English and check all later group text.

### Tests for User Story 4

- [X] T031 [P] [US4] Write `tests/contract/test_group_language.py`: a group first used by a member with a Ukrainian Telegram language gets Ukrainian, otherwise English; `/language` in a group changes it for all members; a member's private language is unaffected, and the group's is unaffected by private changes

### Implementation for User Story 4

- [X] T032 [US4] Make `src/reminder_bot/bot/routers/language.py` change `ctx.chat`'s language through `repo.set_language(ctx.chat_id, …)` and reply in the topic where it was asked

**Checkpoint**: Group language works independently of members' private languages.

---

## Phase 7: Group Lifecycle (Edge Cases, FR-112, FR-115, FR-116)

**Purpose**: Joining, leaving, losing the right to post, supergroup upgrades and deletion after 12 months

### Tests

- [X] T033 [P] Write `tests/contract/test_group_membership.py`: the bot added to a new group stores it with the adder's language and posts the welcome message mentioning `/new`, replying and admin rights (FR-112), and posts it again when added back after `left` or `kicked`; `left`, `kicked`, and `restricted` without `can_send_messages` mark it unreachable; being added back or allowed to post again marks it reachable, and a change only to its admin rights or posting permission posts no welcome; while unreachable nothing is sent; on return, recurring reminders skip ahead with no catch-up and an overdue one-time reminder is sent once with a note (FR-115); channel membership changes store nothing
- [X] T034 [P] Write group cases in `tests/integration/test_dispatcher.py` and `tests/integration/test_maintenance.py`: a `403` or the `400` "not enough rights" and "chat not found" errors mark the group unreachable like a block; `TelegramMigrateToChat` moves the chat and its reminders to the new ID and the send goes out once to the new ID; a group unreachable for 12 months is deleted with its reminders and deliveries, and one unreachable for less isn't
- [X] T035 [P] Write `tests/contract/test_group_migration.py`: a `migrate_to_chat_id` service message moves the chat row, language, reminders and deliveries to the new ID in one step; receiving both the service message and the scheduler error moves it once; no reminder is sent twice or lost (FR-116)

### Implementation

- [X] T036 Add group reachability to `src/reminder_bot/bot/routers/membership.py`: for groups and supergroups, `member` and `administrator`, and `restricted` with `can_send_messages`, call `repo.set_reachable` (creating the chat with the adder's language if new), and post `welcome_group` when the old status was `left` or `kicked`; `left`, `kicked`, and `restricted` without it call `repo.set_unreachable`. Keep the private block handling as it is
- [X] T037 Add `move_chat(old_id, new_id)` to `src/reminder_bot/storage/repositories.py`: in one transaction, insert the new chat row copying `kind`, `language` and `unreachable_at` unless it already exists, point `scheduled_messages.chat_id` at it, and delete the old row; a second call for the same move does nothing
- [X] T038 Create `src/reminder_bot/bot/routers/migration.py` handling messages with `migrate_to_chat_id` by calling `repo.move_chat`, and include it in `src/reminder_bot/bot/app.py` right after `start.router`; make sure `ChatContextMiddleware` lets these service messages through
- [X] T039 Handle group send errors in `src/reminder_bot/scheduler/dispatcher.py`: `TelegramForbiddenError` and `TelegramBadRequest` whose message says the bot can't send, the chat wasn't found or the bot isn't a member call `repo.record_blocked` (now marking the chat unreachable); `TelegramMigrateToChat` calls `repo.move_chat` and `record_retry` so the send repeats to the new ID once. Log only error class names and IDs
- [X] T040 [P] Make `src/reminder_bot/scheduler/maintenance.py` call `delete_chats_unreachable_before`, so private chats and groups both follow the 12-month rule
- [X] T041 [P] Add `welcome_group` and the group `help` text to `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`, as described in contracts/bot-interface.md

**Checkpoint**: Groups survive being left, restricted, re-added and upgraded, and are deleted after 12 months away.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T042 [P] Extend `tests/integration/test_log_privacy.py`: with the bot as a group admin, ordinary group messages and flow answers never appear in logs, and nothing is stored for ordinary messages (FR-113)
- [X] T043 [P] Confirm `tests/unit/test_i18n.py` still checks identical keys and placeholders across `en.py` and `uk.py` with the new group text
- [X] T044 [P] Update `CLAUDE.md`: reminders belong to chats, groups are supported, every flow must end through `flow.end_flow()`, and group handlers send with `ctx.send_kwargs`
- [X] T045 [P] Add pointer notes to the 001 docs: in `specs/001-telegram-reminder-bot/contracts/bot-interface.md`, that flows now clean up their messages (002 FR-119); in `specs/001-telegram-reminder-bot/data-model.md`, that `users` is now `chats` and `user_id` is now `chat_id` (002 data-model.md); each linking to the 002 document
- [X] T046 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest`, and fix anything that fails
- [X] T050 Keep one screen per chat, private and group (FR-124): migration `src/reminder_bot/storage/migrations/0003_screen.sql`, `get_screen` and `set_screen` in `src/reminder_bot/storage/repositories.py`, and `src/reminder_bot/bot/screen.py` (`send_screen`, `show_on_callback`), used by every router for menus, lists, help and results
- [X] T051 [P] Write `tests/contract/test_one_screen.py`: a new screen deletes the previous one and the typed command; edits on the current screen delete nothing; a button on an older message clears the current screen; a saved reminder replaces the menu; a long reminder's two-part screen is deleted together; delivered reminders are never deleted; a group keeps one screen shared by its members, named results included, and without admin rights only members' commands stay; the welcome is replaced by the first screen
- [ ] T047 Review the new Ukrainian text in `src/reminder_bot/i18n/uk.py` with the user
- [ ] T048 Run every check in `specs/002-group-reminders/quickstart.md` on the test bot, including the live-only check that a selective reply prompt opens only for the mentioned member after a button press (research §4), and record the results
- [ ] T049 Deploy to the Oracle server with the user's approval: push, then `git pull && docker compose up -d --build` on the server, and confirm the migration ran and existing private reminders still arrive

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Needs Setup. Blocks all stories. T003 → T004 → T005 → T006 → T007 in order; then T008 → T010 → T011; T012 and T013 can run alongside T008–T011
- **US1 (Phase 3)**: Needs Foundational
- **US2 (Phase 4)**: Needs Foundational. Independent of US1 except that its tests create reminders through the repository
- **US3 (Phase 5)**: Needs US2 (reminders are selected from the list) and US1's flow clean-up (T018)
- **US4 (Phase 6)**: Needs Foundational only
- **Lifecycle (Phase 7)**: Needs Foundational; T039 needs US1's T021 in the same file
- **Polish (Phase 8)**: Needs everything else

### User Story Dependencies

- **US1 (P1)**: The MVP. Stands alone after the foundation
- **US2 (P2)**: Stands alone after the foundation
- **US3 (P3)**: Uses US2's list and US1's clean-up
- **US4 (P3)**: Stands alone after the foundation

### Within Each User Story

- Tests first, confirmed failing
- Routers before text: text tasks marked [P] can be written alongside
- Story checkpoint before moving on

### Parallel Opportunities

- T001 and T002 both edit `tests/conftest.py`, so they run one after the other
- T012 and T013 alongside T008–T011
- All test tasks within a story ([P])
- T021 and T022 alongside T017–T020
- US2 and US4 can proceed in parallel after the foundation
- T033, T034, T035 together; T040 and T041 alongside T036–T039
- T042–T045 together

---

## Parallel Example: User Story 1

```text
# Tests together:
T014 tests/contract/test_group_create.py
T015 tests/contract/test_flow_cleanup.py
T016 tests/integration/test_dispatcher.py (group cases)

# Then, alongside the router work (T017–T020):
T021 src/reminder_bot/scheduler/dispatcher.py (group spacing)
T022 src/reminder_bot/i18n/en.py and uk.py (US1 text)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phases 1 and 2: the rename lands with every 001 test still passing
2. Phase 3: create and deliver group reminders, with clean-up
3. Stop and validate quickstart steps 1–11 on the test bot

### Incremental Delivery

1. Foundation → private chats unchanged, groups recognized
2. US1 → groups can create and receive reminders (MVP)
3. US2 → groups can see their reminders
4. US3 → groups can change and remove them, with names
5. US4 → group language
6. Lifecycle → leaving, restrictions, upgrades, deletion
7. Polish and deployment

Lifecycle work matters before real groups rely on the bot: without it, a group that removes the bot keeps receiving send attempts.

---

## Requirement Coverage

| Requirement | Tasks |
|---|---|
| FR-101, FR-102, FR-103 | T005, T014, T017, T016 |
| FR-104, FR-104a | T010, T013, T014, T017 |
| FR-105 | T010, T014, T019 |
| FR-106 | T005, T014 |
| FR-107, FR-108 | T023, T025 |
| FR-109 | T027, T028, T029 |
| FR-110, FR-111 | T031, T032, T036 |
| FR-110a | T023, T024 |
| FR-112 | T033, T036, T041 |
| FR-113 | T009, T010, T042 |
| FR-114 | T008, T014, T016, T021 |
| FR-115 | T033, T034, T036, T039, T040 |
| FR-116 | T034, T035, T037, T038, T039 |
| FR-117 | T009, T010, T036 |
| FR-118 | T007, T015, T046 |
| FR-119, FR-120 | T013, T015, T018 |
| FR-121, FR-122, FR-123 | T005, T020, T023, T025, T027, T028, T029 |
| SC-101 | T048 |
| SC-102 | T016, T021 |
| SC-103, SC-104 | T023, T024 |
| SC-105 | T014 |
| SC-106 | T007, T046 |
| SC-107 | T015, T048 |

---

## Notes

- Never log group message text or reminder text; log IDs and error class names only
- Every flow ending goes through `flow.end_flow()`; a direct `state.clear()` that ends a flow is a bug
- Commit after each phase checkpoint, when the user asks
