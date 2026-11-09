# Quickstart: Telegram Reminder Bot

This guide shows how to run the bot and prove it works end to end.

## Prerequisites

- `uv` (installs Python 3.14 itself)
- Docker, for container checks
- A **test** bot token from [@BotFather](https://t.me/BotFather), kept separate from production
- A Telegram account to test with, and a second account for the isolation checks

## Set up

```bash
uv sync
```

Copy `.env.example` to `.env` and set `BOT_TOKEN`. See [runtime-config.md](contracts/runtime-config.md) for the other settings.

## Automated checks

```bash
uv run ruff check .
```

```bash
uv run pytest
```

Run one test file or test:

```bash
uv run pytest tests/unit/test_schedule.py
```

```bash
uv run pytest tests/unit/test_schedule.py::test_monthly_short_months
```

**Expected**: All pass. These cover the date rules that can't be practically tested live, such as leap years and Kyiv clock changes (SC-005), using the worked examples in [data-model.md](data-model.md).

## Run the bot

```bash
uv run --env-file .env python -m reminder_bot
```

Or in a container, as it would run on a server:

```bash
docker compose up --build
```

## End-to-end validation

Use the test bot in Telegram. Screens and rules are defined in [bot-interface.md](contracts/bot-interface.md). Set times a few minutes ahead in **Kyiv time**.

| # | Steps | Expected | Spec |
|---|---|---|---|
| 1 | Send `/start` | Actions explained, in Ukrainian if your Telegram is set to Ukrainian, otherwise English | FR-023, FR-023a |
| 2 | Create a one-time message | Confirmation shows Kyiv time; it arrives on time, once, and the list shows it as completed | US1, FR-011 |
| 3 | Try date `31.02.2027`, time `25:70`, and a past date | Each is rejected and only that step repeats | FR-005, FR-005a |
| 4 | Create an Every N days message starting today, a few minutes ahead, every 10 days | Sent today; next send is 10 days later | FR-004 |
| 5 | Open `/list` with more than 10 reminders | Active first, every message reachable by paging | US2 |
| 6 | Edit a message's text and then its time | The next send uses the new values only | US3 |
| 7 | Edit an Every N days message | Asks for both date and interval; cancelling part-way changes nothing | FR-016a, FR-018 |
| 8 | Open a completed message | Only Remove and Back are offered | FR-011 |
| 9 | Remove a message due within minutes | Asks to confirm, and it's never sent | US4 |
| 10 | From a second account, press an old button or view `/list` | Never sees the first account's messages | SC-004 |
| 11 | Change `/language` | All bot text switches; reminder text is unchanged | FR-023a |

## Restart and failure checks

| # | Steps | Expected | Spec |
|---|---|---|---|
| 12 | Schedule a message, stop the bot past its time, restart | Sent once on recovery, after a note with its original time | FR-012, FR-013 |
| 13 | Schedule a daily message, then restart repeatedly around its send time | Never sent twice | FR-010 |
| 14 | Redeploy with `docker compose up --build -d` | Messages remain and are still sent | SC-003 |

## Blocked users

Confirm the assumption in [research.md](research.md) first: the logs for step 15 must show the block being detected as `kicked`, and step 16 as `member`.

| # | Steps | Expected | Spec |
|---|---|---|---|
| 15 | Block the bot while a message is due | No send is attempted | FR-013a |
| 16 | Unblock the bot | Recurring messages resume at their next send, with no catch-up; an overdue one-time message arrives once with a note | FR-013a |

The 12-month deletion, the 100-message limit and the 90-day cleanup are covered by the automated tests, using an injected clock and test data.

## Timing checks

| # | Steps | Expected | Spec |
|---|---|---|---|
| 17 | Time a first-time user creating a message without help | Under 1 minute | SC-001 |
| 18 | Time viewing the list, an update and a removal | Each under 30 seconds | SC-006 |
| 19 | Check handler times in the logs after the full validation run | At least 95% within 2 seconds | SC-007 |

## Deployment readiness

- [ ] All automated checks pass
- [ ] All end-to-end, restart and block checks pass on the test bot
- [ ] Ukrainian text reviewed
- [ ] Production token stored only on the server
- [ ] Logs checked for no reminder text or token
- [ ] Hosting and backup approach decided
