# Quickstart: Group Reminders

How to prove group reminders work end to end. Setup and the automated checks are the same as in the [001 quickstart](../001-telegram-reminder-bot/quickstart.md).

## Prerequisites

- The 001 prerequisites: `uv`, a **test** bot token, and two Telegram accounts (A and B)
- Two test groups with both accounts in them. Make one a group with topics turned on
- In @BotFather, keep **Allow Groups** on and **Group Privacy** on (the defaults)

## Automated checks

```bash
uv run ruff check .
```

```bash
uv run pytest
```

**Expected**: All pass, including every 001 test (SC-106).

## Run the bot

```bash
uv run --env-file .env python -m reminder_bot
```

## Without admin rights

Add the bot to group 1 without making it an admin. Set times a few minutes ahead in Kyiv time.

| # | Steps | Expected | Spec |
|---|---|---|---|
| 1 | Add the bot to group 1 from account A | Welcome message in A's language, mentioning `/new` and admin rights | FR-111, FR-112 |
| 2 | Chat normally in the group | The bot doesn't respond, and nothing about the messages appears in the logs | FR-113 |
| 3 | A sends `/new`, picks Only once | The text question mentions A and opens the reply box only for A | FR-104 |
| 4 | A types an answer without replying | Nothing happens; the question stays open | US1-11 |
| 5 | A replies to each question | Saved, with "Saved by A". A's answers stay; the bot's questions are deleted | US1-9, FR-122 |
| 6 | While A is in a flow, B presses A's recurrence button and replies to A's question | B sees "This isn't your request", and A's flow is unaffected | FR-105 |
| 7 | A and B each run `/new` at the same time | Each reminder gets only its own member's answers | SC-105 |
| 8 | Wait for step 5's reminder | Posted in the group, not in A's private chat | US1-5 |
| 9 | Run `/list` in group 1 and in A's private chat | Each shows only its own reminders | FR-107, SC-103 |

## With admin rights

Make the bot an admin of group 1 with permission to delete messages.

| # | Steps | Expected | Spec |
|---|---|---|---|
| 10 | A creates a reminder, typing answers without replying | Accepted. Afterwards only the confirmation remains | FR-104a, SC-107 |
| 11 | B types during A's flow without replying | Ignored | FR-104a |
| 12 | B opens A's reminder, changes its time, then opens it again | Screen shows "Created by: A" and "Last changed by: B" | FR-121 |
| 13 | B removes it | "Removed by B:" with the text; it's never sent | FR-122, US3-2 |
| 14 | A runs `/language` in the group and picks the other language | All bot text in the group switches; A's private chat keeps its language | US4 |

## Private chat clean-up

| # | Steps | Expected | Spec |
|---|---|---|---|
| 15 | In a private chat, create a reminder, then start another and Cancel | Each time, only the confirmation or "Cancelled" remains | FR-119 |

## Topics

Add the bot to group 2, which has topics.

| # | Steps | Expected | Spec |
|---|---|---|---|
| 16 | Create a reminder from a topic other than General | Questions and confirmation appear in that topic; the reminder is posted in General | FR-114 |

## Lifecycle

| # | Steps | Expected | Spec |
|---|---|---|---|
| 17 | Remove the bot from group 1 while a reminder is due, then add it back | Nothing is sent while it's out. Recurring reminders resume with no catch-up; an overdue one-time reminder is sent once with a note | FR-115 |
| 18 | Stop the bot from sending messages in group 1, let a reminder come due, then allow it again | Same as step 17 | Edge Cases |
| 19 | Upgrade a test group to a supergroup, for example by making it public | Its reminders keep arriving, once each | FR-116 |
| 20 | Add the bot to a channel | Nothing is stored or sent | FR-117 |
| 21 | A presses an old button of group 1 after leaving it (public group) | "This is no longer available" | FR-110a |

## Cancelling and anonymous admins

| # | Steps | Expected | Spec |
|---|---|---|---|
| 22 | In group 1, start `/new`, pick a recurrence, then reply `/cancel` to the text question | The text question says "Send /cancel to stop" and has no Cancel button; the flow ends and is cleaned up | FR-104 |
| 23 | As a group admin with "Remain anonymous" on, send `/new`, then `/list` | `/new` asks to turn off anonymity and starts nothing; `/list` works | Edge Cases |

The 12-month deletion, the 100-reminder limit per group and the 20-per-minute sending are covered by the automated tests.

## Deployment readiness

- [ ] All automated checks pass
- [ ] All checks above pass on the test bot
- [ ] Logs from steps 2, 10 and 11 contain no group message text
- [ ] Ukrainian text for groups reviewed
