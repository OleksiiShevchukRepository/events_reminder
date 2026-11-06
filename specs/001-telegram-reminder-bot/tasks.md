---

description: "Task list for the Telegram Reminder Bot"
---

# Tasks: Telegram Reminder Bot

**Input**: Design documents from `specs/001-telegram-reminder-bot/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The spec's date and no-duplicate rules (SC-003, SC-004, SC-005, FR-010) and the quickstart depend on automated tests, because clock changes, leap years and 12-month periods can't be checked live. Write each test first and confirm it fails before implementing.

**Organization**: Tasks are grouped by user story. US1 works on its own. US3 and US4 select messages from the list built in US2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: The user story the task belongs to

All paths are relative to the repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create `pyproject.toml` with `requires-python = ">=3.14,<3.15"`, dependencies `aiogram>=3.31,<4`, `aiosqlite>=0.22,<1`, `tzdata>=2026.6`, dev dependencies `pytest>=9.2`, `pytest-asyncio>=1.4`, `ruff>=0.17`, a `src/` layout package named `reminder_bot`, pytest `asyncio_mode = "auto"` and Ruff lint and format settings, then run `uv sync` to create `uv.lock`
- [ ] T002 Create the package and test folders from plan.md with empty `__init__.py` files: `src/reminder_bot/` with `domain/`, `storage/`, `bot/`, `bot/routers/`, `scheduler/`, `i18n/`, and `tests/` with `unit/`, `integration/`, `contract/`
- [ ] T003 [P] Create `.gitignore` covering `.env`, `*.db`, `*.db-wal`, `*.db-shm`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` and local backups
- [ ] T004 [P] Create `.env.example` with the variables in contracts/runtime-config.md, with `BOT_TOKEN` left blank

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core parts that every user story needs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Core date and input rules

- [ ] T005 [P] Implement `Clock` protocol, `SystemClock` and a settable `FixedClock`, all returning timezone-aware UTC times, in `src/reminder_bot/clock.py`
- [ ] T006 [P] Write failing schedule tests in `tests/unit/test_schedule.py`: every worked example in data-model.md (include a test named `test_monthly_short_months`), first send strictly after a given moment, monthly return to the original day, yearly 29 February, daily, weekly and interval sequences, a skipped Kyiv time (03:30 on 28.03.2027 gives 04:00) and a repeated Kyiv time (03:30 on 31.10.2027 gives the first occurrence only), and a full year of dates for each recurrence (SC-005)
- [ ] T007 Implement `first_send()` and `next_after()` per the Schedule rules in data-model.md, using `ZoneInfo("Europe/Kyiv")` and always calculating from the start date, in `src/reminder_bot/domain/schedule.py`, until T006 passes
- [ ] T008 [P] Write failing parsing tests in `tests/unit/test_parsing.py`: valid and invalid dates (`7.11.2026`, `07.11.2026`, `31.02.2027`, wrong format, after 31.12.2100), times (`14:45`, `9:05`, `25:70`), intervals (1, 3650, 0, 3651, `1.5`, text), text (blank, exactly and over 4,096 UTF-16 code units, including emoji), and date and time in the past in Kyiv time, including earlier today
- [ ] T009 Implement pure parsing and validation functions that return a value or an error key, in `src/reminder_bot/domain/parsing.py`, until T008 passes

### Configuration and storage

- [ ] T010 [P] Implement environment loading per contracts/runtime-config.md, with a clear startup error if `BOT_TOKEN` is missing or the database location can't be written, in `src/reminder_bot/config.py`
- [ ] T011 [P] Create the `users`, `scheduled_messages` and `deliveries` tables, cascading foreign keys, the message and delivery indexes and the partial unique index from data-model.md in `src/reminder_bot/storage/migrations/0001_initial.sql`
- [ ] T012 Write failing storage tests in `tests/integration/test_db.py`: migrations apply once and are tracked by `PRAGMA user_version`, WAL mode and foreign keys are on, deleting a user cascades, and a second non-`blocked` delivery for the same message and time is rejected
- [ ] T013 Implement connection setup (WAL, foreign keys, busy timeout) and the migration runner in `src/reminder_bot/storage/db.py` until T012 passes
- [ ] T014 Implement user queries (get or create, set language, set or clear `blocked_at`) in `src/reminder_bot/storage/repositories.py`

### Languages and bot shell

- [ ] T015 [P] Write a failing test that `en` and `uk` have identical keys and placeholders in `tests/unit/test_i18n.py`
- [ ] T016 Implement `translate(language, key, **values)` in `src/reminder_bot/i18n/__init__.py` with start, help, menu, cancel and "no longer available" text in `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`, until T015 passes
- [ ] T017 Create shared test fixtures in `tests/conftest.py`: temporary migrated database, `FixedClock`, and a fake aiogram session that records outgoing API calls and can return chosen errors
- [ ] T018 Write failing tests in `tests/contract/test_start.py`: `/start` registers a new user, `uk` gives Ukrainian and anything else English, the stored language isn't overwritten later, `/help` mentions Kyiv time, `/cancel` ends a flow, and group chat updates are ignored and store nothing
- [ ] T019 Implement middleware that ignores non-private updates, gets or creates the user and provides their language to handlers in `src/reminder_bot/bot/middleware.py`
- [ ] T020 Add the main menu keyboard and callback data formats from contracts/bot-interface.md in `src/reminder_bot/bot/keyboards.py`
- [ ] T021 Implement `/start`, `/help`, `/cancel` and a shared handler for commands sent during a flow in `src/reminder_bot/bot/routers/start.py`, until T018 passes
- [ ] T022 Implement the entry point with stdout logging, migrations, long polling with `allowed_updates` of `message`, `callback_query` and `my_chat_member`, SIGTERM handling and handler timing logs in `src/reminder_bot/__main__.py`

**Checkpoint**: The bot starts, answers `/start`, and has tested date and input rules

---

## Phase 3: User Story 1 - Create a scheduled message and receive it (Priority: P1) 🎯 MVP

**Goal**: A user creates a message of any recurrence type through the guided flow, and it arrives on time, exactly once, even after a restart.

**Independent Test**: Create a one-time message a few minutes ahead and a weekly message. The first arrives at the chosen Kyiv time, and the second is confirmed with the correct next send date.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T023 [P] [US1] Write create flow tests in `tests/contract/test_create_flow.py`: full flow for each recurrence type, Every N days asks for an interval, invalid input repeats only its step, Cancel saves nothing, non-text input is rejected, past dates are rejected for every recurrence, confirmation shows "Kyiv time" and the next send, and the limit of 100 is enforced at flow start and at save, with completed messages not counted
- [ ] T024 [P] [US1] Write dispatcher tests in `tests/integration/test_dispatcher.py`: recurring messages advance, one-time messages stay active until their delivery ends and then complete, no second claim for the same send, missed sends collapse into one, a note goes first when more than 1 minute late and not otherwise, text is sent with no parse mode, each row of the failure table in research.md, `retrying` sends continue past 1 hour and resume after a restart, a recurring message that comes due during a retry adds no new delivery, leftover `sending` records become `unknown` and aren't resent, blocked users are skipped, and a message edited or removed at the moment it's due is either sent in its previous form or handled under the new values, never both
- [ ] T025 [P] [US1] Write block handling tests in `tests/integration/test_membership.py`: `kicked` sets and `member` clears `blocked_at`, recurring messages move to a future send with no catch-up on unblock, overdue one-time messages stay due, and a 403 returns a claimed one-time message to `active` so it can be claimed again
- [ ] T026 [P] [US1] Write maintenance tests in `tests/integration/test_maintenance.py`: a user is deleted after exactly 12 calendar months blocked and not before, unblocking resets the period, delivery records are deleted after 90 days, and only 7 days of backups are kept
- [ ] T027 [P] [US1] Write language tests in `tests/contract/test_language.py`: `/language` offers both languages, all later text uses the chosen one, and reminder text is unchanged

### Implementation for User Story 1

- [ ] T028 [US1] Add message creation with an in-transaction limit check, active message count, due message and due retry queries, claim, outcome recording with one-time completion, retry scheduling, return of a blocked one-time message, unblock rescheduling and leftover `sending` handling, per data-model.md and the Delivery section of research.md, in `src/reminder_bot/storage/repositories.py`
- [ ] T029 [P] [US1] Define the create flow states in `src/reminder_bot/bot/states.py`
- [ ] T030 [US1] Add recurrence, Cancel and language buttons in `src/reminder_bot/bot/keyboards.py`
- [ ] T031 [US1] Add English and Ukrainian text for the create flow, validation errors, confirmations, recurrence names, the overdue note and the limit message in `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`
- [ ] T032 [US1] Implement the create flow per contracts/bot-interface.md, including the check that date and time together are in the future, in `src/reminder_bot/bot/routers/create.py`, until T023 passes
- [ ] T033 [P] [US1] Implement `/language` and its buttons in `src/reminder_bot/bot/routers/language.py`, until T027 passes
- [ ] T034 [P] [US1] Implement block and unblock handling from `my_chat_member` updates in `src/reminder_bot/bot/routers/membership.py`, with the status assumption logged so it can be confirmed live
- [ ] T035 [US1] Implement the 5-second loop, claim-then-send, the failure table, saved retries, the overdue note, the shared rate limiter with an injectable clock (25 per second overall, about 1 per second per chat, pause on `retry_after`), the heartbeat file and draining in-flight sends on shutdown in `src/reminder_bot/scheduler/dispatcher.py`, until T024 and T025 pass
- [ ] T036 [US1] Implement daily blocked-user deletion, 90-day delivery record cleanup and daily database backups with 7 days kept in `src/reminder_bot/scheduler/maintenance.py`, until T026 passes
- [ ] T037 [US1] Wire the new routers, dispatcher, maintenance job, leftover `sending` handling at startup and per-language `setMyCommands` into `src/reminder_bot/__main__.py`

**Checkpoint**: A user can create messages and receive them. This is a usable MVP, validated by quickstart.md checks 1–4 and 12–16

---

## Phase 4: User Story 2 - See all scheduled messages (Priority: P2)

**Goal**: A user sees all of their messages, in order, and can open any one to read its full text.

**Independent Test**: Create several messages with different recurrences, request the list, and check that all of them appear with correct details.

### Tests for User Story 2

- [ ] T038 [P] [US2] Write list tests in `tests/contract/test_list.py`: active messages first by next send date, then completed; paging at 5 reaches every message; preview, recurrence, time, next send date and status are shown; a one-time message being sent shows "Sending" and one that failed permanently shows "Not delivered"; full text appears on the message screen; the empty list offers New message; and one user can't list or open another user's message, getting the same "no longer available" answer as for a removed message

### Implementation for User Story 2

- [ ] T039 [US2] Add a paged list query and a message lookup scoped by user in `src/reminder_bot/storage/repositories.py`
- [ ] T040 [US2] Add list paging and message screen buttons, with the correct set for active, active `interval` and completed messages, in `src/reminder_bot/bot/keyboards.py`
- [ ] T041 [US2] Add English and Ukrainian text for the list, message screen and empty state in `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`
- [ ] T042 [US2] Implement `/list`, paging and the message screen in `src/reminder_bot/bot/routers/list.py` and register it in `src/reminder_bot/__main__.py`, until T038 passes

**Checkpoint**: Users can create, receive and review messages. Validated by quickstart.md checks 5 and 10

---

## Phase 5: User Story 3 - Update a scheduled message (Priority: P3)

**Goal**: A user changes a message's text, recurrence, date or time, and later sends use only the new values.

**Independent Test**: Change the text, the recurrence and the time of an existing message one at a time, and check that the next send uses the new values.

### Tests for User Story 3

- [ ] T043 [P] [US3] Write update tests in `tests/contract/test_update.py`: each row of "What sets `next_send_at`" in data-model.md; a text edit leaves the schedule unchanged; Every N days always asks for both date and interval, saving neither until both are valid; switching to Only once or Every N days asks for a new date; past values and Cancel leave the message unchanged; completed messages can't be updated; and another user's message can't be updated

### Implementation for User Story 3

- [ ] T044 [US3] Add update functions that re-check owner and `active` status and recalculate `next_send_at` in one transaction in `src/reminder_bot/storage/repositories.py`
- [ ] T045 [US3] Add the update flow states in `src/reminder_bot/bot/states.py`
- [ ] T046 [US3] Add English and Ukrainian text for update prompts and confirmations in `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`
- [ ] T047 [US3] Implement the update flows per contracts/bot-interface.md in `src/reminder_bot/bot/routers/update.py` and register them in `src/reminder_bot/__main__.py`, until T043 passes

**Checkpoint**: Validated by quickstart.md checks 6–8

---

## Phase 6: User Story 4 - Remove a scheduled message (Priority: P3)

**Goal**: A user permanently removes a message after confirming, and it's never sent again.

**Independent Test**: Remove a message that is due in a few minutes and check that it isn't sent and no longer appears in the list.

### Tests for User Story 4

- [ ] T048 [P] [US4] Write removal tests in `tests/contract/test_remove.py`: confirming deletes the message and its delivery records; Keep changes nothing; a removed message is never claimed; active and completed messages can both be removed; removing frees a place under the limit; an old button answers "no longer available"; and another user's message can't be removed

### Implementation for User Story 4

- [ ] T049 [US4] Add deletion scoped by user in `src/reminder_bot/storage/repositories.py`
- [ ] T050 [US4] Add English and Ukrainian text for removal in `src/reminder_bot/i18n/en.py` and `src/reminder_bot/i18n/uk.py`
- [ ] T051 [US4] Implement the remove flow with confirmation buttons in `src/reminder_bot/bot/routers/remove.py` and register it in `src/reminder_bot/__main__.py`, until T048 passes

**Checkpoint**: All user stories work. Validated by quickstart.md check 9

---

## Phase 7: Packaging

**Purpose**: Run the bot in a container

- [ ] T052 [P] Create a `Dockerfile` using a Python 3.14 slim image and `uv.lock`, running as a non-root user that can write to `/data`
- [ ] T053 [P] Create `compose.yaml` per contracts/runtime-config.md: `restart: unless-stopped`, a named volume at `/data`, `env_file: .env`, a 30-second stop grace period, a health check on the heartbeat file, and no published ports
- [ ] T054 Run the `docker compose up --build` and redeployment checks in `specs/001-telegram-reminder-bot/quickstart.md`, confirming messages survive a rebuild (check 14)
---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Checks that span all stories

- [ ] T055 [P] Add a test that runs the create and send paths and asserts no reminder text or token appears in logs, in `tests/integration/test_log_privacy.py`
- [ ] T056 [P] Add a test that 1,500 messages due in the same minute, across different users, are all sent within 1 minute of simulated time by a fake session, respecting the rate limiter (SC-002), in `tests/integration/test_dispatch_load.py`
- [ ] T057 **Needs your review.** Review all Ukrainian wording in `src/reminder_bot/i18n/uk.py`
- [ ] T058 Replace the "planned" notes in `CLAUDE.md` with the confirmed commands and architecture
- [ ] T059 Run `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest`, then complete every check in `specs/001-telegram-reminder-bot/quickstart.md` on a test bot, including the timing checks and confirming the `kicked` and `member` block statuses in research.md, and record any differences in `specs/001-telegram-reminder-bot/research.md`

---

## Phase 9: Production Deployment (FR-024)

**Purpose**: Put the bot on a server. Do this only after every earlier phase passes.

- [ ] T060 **Needs your decision and approval.** Choose the hosting provider, provide the production BotFather token and server access, decide whether backups are copied off the server, then deploy with `compose.yaml` and record the deployment and update steps in `README.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup, and blocks all user stories
- **US1 (Phase 3)**: Depends on Foundational
- **US2 (Phase 4)**: Depends on Foundational; can be tested with messages created directly in the database
- **US3 and US4 (Phases 5–6)**: Depend on US2's list and message screen; independent of each other
- **Packaging (T052–T054)**: Depends on US1, ideally on all stories
- **Polish (Phase 8)**: Depends on all desired stories
- **Production deployment (T060)**: Last, after T054 and T059

### User Story Dependencies

```text
Setup → Foundational → US1 (MVP)
                     → US2 → US3
                           → US4
                     all → Packaging → Polish → T060 deploy
```

### Within Each User Story

- Tests are written first and must fail
- Repository functions come before flows
- Text and buttons come before the routers that use them
- `src/reminder_bot/storage/repositories.py`, `keyboards.py`, `states.py`, `__main__.py` and the i18n files are shared, so tasks touching them run one at a time

### Parallel Opportunities

- **Phase 1**: T003, T004
- **Phase 2**: T005, T006, T008, T010, T011, T015 (T007 and T009 can also run side by side once their tests exist)
- **US1**: T023–T027 together; then T029, T033, T034
- **After US2**: US3 and US4 can run in parallel, apart from their shared files
- **Phases 7–8**: T052, T053, T055, T056

---

## Parallel Example: User Story 1

```bash
# Write all User Story 1 tests together:
Task: "Create flow tests in tests/contract/test_create_flow.py"
Task: "Dispatcher tests in tests/integration/test_dispatcher.py"
Task: "Block handling tests in tests/integration/test_membership.py"
Task: "Maintenance tests in tests/integration/test_maintenance.py"
Task: "Language tests in tests/contract/test_language.py"

# Then implement the separate files together:
Task: "Flow states in src/reminder_bot/bot/states.py"
Task: "Language router in src/reminder_bot/bot/routers/language.py"
Task: "Membership router in src/reminder_bot/bot/routers/membership.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup and Foundational
2. Complete User Story 1
3. **Stop and validate** on a test bot with quickstart.md checks 1–4 and 12–16

The MVP can't list, edit or remove messages, so a mistaken recurring reminder couldn't be stopped. Add at least US2 and US4 before real users try it.

### Incremental Delivery

1. Setup + Foundational: the bot runs and the date rules are proven
2. US1: messages are created and delivered
3. US2: messages can be reviewed
4. US3 and US4: messages can be changed and removed, which completes the spec
5. Packaging, polish, then production deployment

## Requirement Coverage

| Requirement | Tasks |
|---|---|
| FR-001, FR-001a | T023, T032, T047 |
| FR-002, FR-003, FR-004 | T006, T007, T008, T009, T023, T032 |
| FR-005, FR-005a, FR-006 | T008, T009, T023, T032, T043 |
| FR-007, FR-007a, FR-009 | T006, T007, T024, T035 |
| FR-008, FR-010, FR-012, FR-013 | T012, T024, T028, T035, T054 |
| FR-011 | T024, T028, T038, T043 |
| FR-013a | T025, T026, T034, T036 |
| FR-014, FR-015 | T038, T039, T042 |
| FR-016, FR-016a, FR-017, FR-018 | T043, T044, T047 |
| FR-019 | T048, T049, T051 |
| FR-020, FR-023, FR-023a | T015, T016, T018, T021, T027, T033, T057 |
| FR-020a | T023, T028, T048 |
| FR-021 | T038, T039, T043, T048 |
| FR-022 | T007, T008, T023 |
| FR-024 | T052, T053, T060 |
| SC-001, SC-006, SC-007 | T022, T059 (quickstart timing checks 17–19) |
| SC-002 | T035, T056 |
| SC-003 | T024, T054 |
| SC-004 | T038, T043, T048 |
| SC-005 | T006 |

## Notes

- [P] tasks touch different files and don't depend on unfinished tasks
- Commit after each task or logical group
- Stop at any checkpoint to validate a story on its own
- T057 and T060 need you; everything else can be done without further input, given a test bot token for T059
