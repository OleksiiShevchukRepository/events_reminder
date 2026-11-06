# Data Model: Telegram Reminder Bot

All stored timestamps are UTC. Kyiv time is used only for input, display and schedule calculation. Foreign keys are enforced, and deletes cascade.

## users

| Field | Type | Rules |
|---|---|---|
| `id` | integer, primary key | Telegram user ID. In a private chat this is also the chat ID. |
| `language` | text | `en` or `uk`. Set on first contact, then changed only by the user. |
| `blocked_at` | timestamp, nullable | Set when the user blocks the bot, cleared on unblock. |
| `created_at` | timestamp | |

**Spec**: FR-013a, FR-020, FR-023a.

## scheduled_messages

| Field | Type | Rules |
|---|---|---|
| `id` | integer, primary key | |
| `user_id` | integer, foreign key | Owner. All user-facing queries filter on this (FR-021). |
| `text` | text | Not blank, at most 4,096 UTF-16 code units. Stored as entered. |
| `recurrence` | text | `once`, `daily`, `weekly`, `monthly`, `yearly` or `interval`. |
| `start_date` | date | Kyiv calendar date. The anchor for all repeats. |
| `send_time` | time | Kyiv time, hours and minutes. |
| `interval_days` | integer, nullable | 1–3,650 when `recurrence = interval`, otherwise null. |
| `next_send_at` | timestamp, nullable | Set when `active`, null when `completed`. |
| `status` | text | `active` or `completed`. |
| `created_at`, `updated_at` | timestamp | |

**Indexes**: `(status, next_send_at)` for the scheduler; `(user_id, status, next_send_at)` for lists and the limit check.

**Spec**: FR-002 to FR-007a, FR-011, FR-016, FR-020a.

## deliveries

Stores no message text.

| Field | Type | Rules |
|---|---|---|
| `id` | integer, primary key | |
| `message_id` | integer, foreign key | Deleted along with its message. |
| `scheduled_at` | timestamp | The send this record belongs to. |
| `sent_at` | timestamp, nullable | When Telegram accepted it. |
| `status` | text | `sending`, `sent`, `failed`, `unknown` or `blocked`. |
| `error` | text, nullable | Short error code, never message content. |
| `created_at` | timestamp | Used for the 90-day cleanup. |

**Uniqueness**: A partial unique index on `(message_id, scheduled_at)` where `status != 'blocked'`. This prevents duplicate sends (FR-010) while still letting a one-time message returned by a block be claimed again.

## Message states

```text
create ──► active ──(one-time message claimed for sending)──► completed ──(user removes)──► deleted
             │  ▲
             │  └─(one-time message hits 403: back to active at its original time)
             │
             ├─(recurring message sent: stays active, next_send_at advances)
             └─(user removes)──► deleted
```

- `completed` is final. These messages can only be removed, not updated (FR-011).
- Only `once` messages can become `completed`. Recurring messages have no end date (FR-007a).
- Only `active` messages count towards the limit of 100 (FR-020a).

## Schedule rules

`next_after(message, moment)` returns the first send strictly after `moment`, calculated from `start_date`:

| Recurrence | Send dates |
|---|---|
| `once` | `start_date` only |
| `daily` | `start_date` + k days |
| `weekly` | `start_date` + 7k days |
| `interval` | `start_date` + k × `interval_days` days |
| `monthly` | Same day of the month as `start_date`, or the month's last day if shorter |
| `yearly` | Same day and month as `start_date`; 29 February becomes 28 February in non-leap years |

Each date is combined with `send_time` in `Europe/Kyiv`, then converted to UTC:
- **Skipped time**: The first valid moment after the gap.
- **Repeated time**: The first occurrence only.

**Worked examples** (these become unit tests):

| Case | Expected sends |
|---|---|
| Interval from 7.11.2026, every 10 days | 7.11, 17.11, 27.11, 7.12.2026 |
| Monthly from 29.01.2027 | 29.01, 28.02, 29.03.2027; 29.02.2028 |
| Monthly from 31.01.2027 | 31.01, 28.02, 31.03, 30.04, 31.05.2027 |
| Yearly from 29.02.2028 | 29.02.2028, 28.02.2029 |

## What sets `next_send_at`

| Event | Result |
|---|---|
| Create | The first send, at `start_date` and `send_time`. |
| Recurring send claimed | `next_after(now)`, so missed sends collapse into one (FR-013). |
| One-time send claimed | Null, and status becomes `completed`. |
| Text updated | Unchanged. |
| Send time updated | `next_after(now)` with the new time, keeping `start_date`. For `once`, the new date and time must be in the future. |
| Date updated (`daily`, `weekly`, `monthly`, `yearly`) | The first send on the new date. |
| Date and interval updated (`interval`) | Both are required together. The first send is on the new date (FR-016a). |
| Recurrence switched to `daily`, `weekly`, `monthly` or `yearly` | `next_after(now)` from the existing `start_date`, or the start date itself if it's still ahead. |
| Recurrence switched to `once` or `interval` | Asks for a new date, plus an interval for `interval` (FR-016a). |
| User unblocks | Recurring: `next_after(now)`. One-time: unchanged, so it goes out once as overdue. |

## Validation

Full input rules and messages are in [contracts/bot-interface.md](contracts/bot-interface.md).

| Input | Rule | Spec |
|---|---|---|
| Date | Real calendar date in `D.M.YYYY` format, up to 31.12.2100 | FR-001a |
| Time | Valid 24-hour time in `H:MM` format | FR-001a |
| Date and time together | Not in the past in Kyiv time, including earlier today | FR-005a, FR-022 |
| Interval | Whole number, 1–3,650 | FR-004 |
| Text | Text content only, not blank, within the length limit | FR-005 |
| Active message count | Fewer than 100 at start of creation and again at save | FR-020a |

## Cleanup

| Data | When it's deleted |
|---|---|
| Message and its delivery records | When the user removes it. |
| User, messages and delivery records | After 12 continuous calendar months blocked. |
| Delivery records | After 90 days. |
| Daily database backups | After 7 days, so deleted data leaves backups within a week. |
