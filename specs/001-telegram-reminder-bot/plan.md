# Implementation Plan: Telegram Reminder Bot

**Branch**: `main` (no feature branch, by choice) | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-telegram-reminder-bot/spec.md`

## Summary

A Telegram bot that lets any user create, list, update and remove scheduled messages through guided, button-based chats in English or Ukrainian. Messages go out at a set Kyiv time, either once or repeating with no end date: daily, weekly, monthly, yearly or every N days.

The bot is a single Python process with two concurrent parts: a Telegram long-polling handler and a scheduler loop. They share a SQLite database, which keeps schedules safe across restarts. Schedule calculation is a pure, heavily tested module, because date correctness is the bot's core promise. It deploys as one Docker container on a small Linux server. See [research.md](research.md) for the reasoning behind each choice.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: aiogram 3.31 (Telegram framework), aiosqlite 0.22 (async SQLite), tzdata (time zone rules, so `Europe/Kyiv` also resolves on Windows)

**Storage**: SQLite in WAL mode, one file on a persistent volume, accessed with plain SQL and numbered migrations

**Testing**: pytest with pytest-asyncio; Ruff for linting and formatting

**Target Platform**: Linux server running Docker Compose; development on Windows with `uv`

**Project Type**: Long-running service (Telegram bot)

**Performance Goals**: 99% of messages sent within 1 minute of their time (SC-002); 95% of user actions answered within 2 seconds (SC-007)

**Constraints**: Telegram allows about 30 messages per second overall and about 1 per second per chat, and 1–4,096 characters per message. Only one process can poll a bot token at a time. There must be no duplicate sends (FR-010).

**Scale/Scope**: Designed for up to a few thousand users, with at most 100 active messages each (FR-020a). A peak of about 1,800 messages per minute is the ceiling set by Telegram's limit.

## Project Structure

### Documentation (this feature)

```text
specs/001-telegram-reminder-bot/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Technology and design decisions
├── data-model.md        # Tables, validation, state changes, schedule rules
├── quickstart.md        # Setup and end-to-end validation guide
├── contracts/
│   ├── bot-interface.md   # Commands, buttons, flows, Telegram updates
│   └── runtime-config.md  # Environment variables and container behavior
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Created by /speckit-tasks, not by this command
```

### Source Code (repository root)

```text
src/reminder_bot/
├── __main__.py          # Entry point: starts polling, scheduler and cleanup jobs
├── config.py            # Reads and validates environment variables
├── clock.py             # Injectable current time, used in tests
├── domain/
│   ├── schedule.py      # Pure next-send calculation, including Kyiv clock changes
│   └── parsing.py       # Pure parsing and validation of dates, times, intervals, text
├── storage/
│   ├── db.py            # Connection setup and migration runner
│   ├── migrations/      # Numbered .sql files
│   └── repositories.py  # All SQL, always scoped by user for user-facing queries
├── bot/
│   ├── routers/         # Handlers: start/menu, create, list, update, remove, language, membership
│   ├── states.py        # Guided flow states
│   └── keyboards.py     # Inline buttons and callback data
├── scheduler/
│   ├── dispatcher.py    # Claims due messages and sends them
│   └── maintenance.py   # Blocked-user deletion, delivery record cleanup, backups
└── i18n/
    ├── en.py            # English text
    └── uk.py            # Ukrainian text

tests/
├── unit/                # schedule, parsing, i18n key parity
├── integration/         # repositories, dispatcher and handlers with a temp database
└── contract/            # bot-interface behavior through a fake Telegram session

Dockerfile
compose.yaml
pyproject.toml
.env.example
```

**Structure Decision**: One Python package with a `src/` layout. Dependencies point inward: `bot` and `scheduler` use `storage` and `domain`, and `domain` depends on nothing, so the date rules can be tested without Telegram or a database.

## How the Parts Work Together

1. **Handlers** run the guided flows. Each flow is held in memory until its final step, then saved in one database transaction. A restart mid-flow discards it, which matches the spec's abandoned input rule.
2. **Scheduler** checks every 5 seconds for due messages. For each, one transaction records the delivery attempt and advances the schedule; the message is sent only after that commit. This order is what prevents duplicate sends. See the Delivery section of [research.md](research.md).
3. **Maintenance** runs daily: it deletes data for users blocked for 12 months, removes old delivery records and makes a database backup.

## Decisions to Confirm

These go beyond the spec or need your input. Each is explained in [research.md](research.md).

| Decision | Choice in this plan |
|---|---|
| Hosting provider | Any small Linux server with Docker. No provider is chosen yet, and you'd need to provide the account and the BotFather token. |
| Crash during a send | Never resend if the outcome is unknown. In rare cases this can lose one send instead of duplicating it. |
| Off-server backups | Daily backups stay on the server, so they won't survive losing the server itself. |
| Input limits | Interval of at most 3,650 days and dates up to the year 2100. The spec sets no maximum. |
| List display | Lists show a short text preview, with the full text on the message's own screen. |
| Ukrainian wording | I'll draft the text, and it needs a review by you. |

## Complexity Tracking

No unusual complexity needs justifying: one package, one process and one database file.
