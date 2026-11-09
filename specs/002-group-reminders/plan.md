# Implementation Plan: Group Reminders

**Branch**: `main` (no feature branch, by choice) | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-group-reminders/spec.md`

## Summary

Let the bot work in Telegram groups as well as private chats. Group members create, list, change and remove the group's own reminders with the same guided steps, and the bot posts them in the group. Flows clean up their questions and answers when they end, in groups and private chats alike.

The core change is that reminders belong to a **chat** instead of a user. A private chat's ID is the person's ID, so existing data carries over unchanged, and every existing rule (limit, language, pausing when unreachable, deletion after 12 months, scoping every query) applies to groups for free. Around that sit group-specific pieces: a chat context for handlers, reply prompts that target one member, a membership check on button presses, flow clean-up, join and leave handling, and the supergroup upgrade. See [research.md](research.md) for each decision.

## Technical Context

**Language/Version**: Python 3.14 (unchanged)

**Primary Dependencies**: aiogram 3.31, aiosqlite 0.22, tzdata (unchanged; no new dependencies)

**Storage**: The same SQLite file. One new migration, `0002_chats.sql`, renames `users` to `chats` and `user_id` to `chat_id`, and adds `kind`, `created_by_name` and `changed_by_name`. See [data-model.md](data-model.md)

**Testing**: pytest with pytest-asyncio and the fake Telegram session, extended for groups, members, topics, message deletion and membership checks

**Target Platform**: The existing Docker Compose deployment on the Oracle server. No new settings

**Project Type**: Long-running service (Telegram bot)

**Performance Goals**: 99% of group reminders sent within 1 minute when up to 20 are due in one group at once (SC-102). 95% of actions answered within 2 seconds, including the membership check (001 SC-007)

**Constraints**: About 20 messages per minute per group from Telegram. Bots can delete messages only up to 48 hours old, and members' messages in groups only as admins. Telegram's default group privacy mode stays on, so the bot sees only commands and replies unless it's an admin. Ordinary group messages must never be stored or logged (FR-113)

**Scale/Scope**: Groups count towards the same totals as private chats: up to a few thousand chats, at most 100 active reminders each

## Project Structure

### Documentation (this feature)

```text
specs/002-group-reminders/
├── spec.md
├── plan.md              # This file
├── research.md          # Decisions
├── data-model.md        # Migration and entity changes
├── quickstart.md        # Live validation in groups
├── contracts/
│   └── bot-interface.md # What changes in groups
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root)

Existing files that change, and the few new ones:

```text
src/reminder_bot/
├── __main__.py              # Register commands for the group chat scope too
├── storage/
│   ├── migrations/
│   │   └── 0002_chats.sql   # NEW
│   └── repositories.py      # Chat in place of User; names; group join, move and reachability
├── bot/
│   ├── context.py           # NEW: ChatContext (chat, topic, member) built by the middleware
│   ├── flow.py              # NEW: ask(), track(), end_flow() for prompts and clean-up
│   ├── middleware.py        # Groups allowed; drops ordinary group chat; membership check
│   ├── keyboards.py         # Reply prompt for group questions
│   ├── views.py             # Created/changed lines on group screens
│   └── routers/
│       ├── start.py         # Group help; every flow ending goes through end_flow()
│       ├── create.py        # Send to ctx; prompts via ask(); names saved
│       ├── update.py        # Same, plus changed_by_name
│       ├── remove.py        # "Removed by" confirmation in groups
│       ├── list.py          # Lists by chat
│       ├── language.py      # Sets the chat's language
│       ├── membership.py    # Group join, leave, restrict; welcome message
│       ├── migration.py     # NEW: supergroup upgrade
│       └── fallback.py      # Silent in groups; "not your request" for others' buttons
├── scheduler/
│   ├── dispatcher.py        # Sends to chats; group spacing; unreachable and upgrade errors
│   └── maintenance.py       # Deletes unreachable chats after 12 months
└── i18n/
    ├── en.py                # Group texts
    └── uk.py

tests/
├── conftest.py              # Group chats, members, topics, deletions, membership
├── integration/             # Migration, repositories by chat, dispatcher to groups
└── contract/                # Group flows, isolation, clean-up, names, lifecycle
```

**Structure Decision**: Same package and layering as 001. The `domain/` date and parsing rules don't change. The rename from user to chat touches many files, but mechanically, and doing it first keeps every later step small.

## How the Parts Work Together

1. **Middleware** works out where an update came from. It ignores channels, and in groups it drops anything that isn't the bot's command, a button press or an answer from a member with an active flow. For the rest it loads or creates the chat, checks membership for group button presses, and gives handlers a `ChatContext` and a translator in the chat's language.
2. **Flows** ask each question through `ask()`. In groups, `ask()` mentions the member and attaches a reply prompt. It also records message IDs for clean-up. Every way a flow can end goes through `end_flow()`, which deletes those messages before the final reply.
3. **Repositories** scope every query by chat ID, and save the member's name on group reminders.
4. **Scheduler** sends due reminders to their chat. Groups get General-topic posts, 3-second spacing, and the same pause, retry and unreachable rules as blocked private chats, plus the supergroup move.
5. **Membership and migration handlers** keep each group's reachability and ID current.

## Implementation Order

1. Migration and the rename from user to chat, with every 001 test passing unchanged.
2. Chat context, group middleware rules and commands, with nothing stored for ordinary chat.
3. Group create flow with reply prompts and member-only input (US1).
4. Flow clean-up in groups and private chats.
5. Group list, membership check, update and remove with names (US2, US3).
6. Group language and welcome message (US4).
7. Scheduler and lifecycle: group sending, unreachable groups, upgrade, deletion after 12 months.

## Decisions to Confirm

| Decision | Choice in this plan |
|---|---|
| Storage shape | Rename `users` to `chats` rather than adding a separate groups table (research §1) |
| Starting command | The member's `/new` message is deleted with the flow's answers, not only the answers |
| Anonymous admins | Treated as one member named "Group admin", so they can use the bot |
| Others pressing flow buttons | A short "This isn't your request" notice instead of complete silence, so they know why nothing happened |
| Live-only check | A reply prompt that targets one member after a button press must be confirmed on a real bot (research §4) |

## Complexity Tracking

No unusual complexity: still one package, one process and one database file. The only cross-cutting change is the rename from user to chat, which is deliberate and lets groups reuse every existing rule.
