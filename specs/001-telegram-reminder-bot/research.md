# Research: Telegram Reminder Bot

Package versions were checked on PyPI on 2026-11-06 and confirmed to resolve together on Python 3.14 with binary wheels. They haven't been installed or run yet. Telegram facts come from the [Bots FAQ](https://core.telegram.org/bots/faq) and [Bot API](https://core.telegram.org/bots/api).

## Language and framework

**Decision**: Python 3.14 with aiogram 3.31.

**Rationale**: aiogram is async, so one process can handle chats and scheduling together. It includes the guided-flow state machine, routers and inline buttons that this bot needs. Python's `zoneinfo` handles Kyiv clock changes in the standard library, and 3.14 is already installed through `uv` on the development machine.

**Alternatives considered**: python-telegram-bot 22.8 is also suitable; aiogram's built-in flow handling fits the guided design slightly better. Node.js with grammY would work too, but would need a separate date library.

## Storage

**Decision**: One SQLite file in WAL mode, with aiosqlite and plain SQL, on a Docker volume.

**Rationale**: There is one process and modest scale, so a database server would add running cost and upkeep without benefit. SQLite's transactions provide the atomic claim that FR-010 relies on, and the data survives restarts (FR-012). Tests can use real temporary databases.

**Alternatives considered**: PostgreSQL would be needed for several bot processes, which this design doesn't have. An ORM adds little for a handful of tables.

**Migrations**: Numbered `.sql` files run at startup and are tracked with `PRAGMA user_version`.

## Scheduling

**Decision**: A custom loop that checks the database every 5 seconds for active messages with `next_send_at <= now`, stored in UTC and indexed.

**Rationale**: The database stays the only record of what's due, so restart recovery (FR-013) needs no extra code: overdue rows are simply picked up. A 5-second check comfortably meets the 1-minute target in SC-002.

**Alternatives considered**: APScheduler would add a second copy of the schedule to keep in sync with the database, and its recurrence rules don't match the spec's short-month rules. Cron can't handle per-user schedules.

## Date calculation

**Decision**: A pure function returns the first send strictly after a given moment, always computed from the original start date and never from the previous send.

**Rationale**: Calculating from the start date is what lets a monthly message on the 31st return to the 31st after a shorter month. If it were computed from the previous send, it would drift to the 28th permanently. See [data-model.md](data-model.md) for the rules.

**Kyiv clock changes**: Use `ZoneInfo("Europe/Kyiv")`.
- **Skipped times**: Python would shift a skipped time forward by the size of the gap, so 03:30 becomes 04:30. The spec requires the next valid time, so the function detects the gap and returns 04:00.
- **Repeated times**: Using `fold=0` picks the first occurrence, so the message is sent once.
- **Rule changes**: If Ukraine changes its clock rules, updating `tzdata` and redeploying corrects future calculations. Each message's single already-stored next send could still be off by an hour, which is accepted.

## Delivery: no duplicates, and failures

**Decision**: Claim first, then send.
1. In one `BEGIN IMMEDIATE` transaction, insert a delivery record with status `sending` and advance the schedule. For a one-time message, mark it `completed` instead.
2. Commit, then call Telegram.
3. Record the outcome.

A unique index on message and scheduled time blocks a second claim.

**Failure handling**:

| Result from Telegram | Action |
|---|---|
| Success | Record `sent` |
| 429 flood limit | Wait for the returned `retry_after`, then retry |
| Connection could not be made, or a 5xx error | Retry with backoff for up to 1 hour, then record `failed` |
| Read timeout (the outcome is unknown) | Record `unknown`, don't retry |
| 403 blocked | Set the user's `blocked_at` and handle it as described under Blocked users |
| Other 4xx | Record `failed` and log it |
| Process restarts with a record still `sending` | Mark it `unknown`, don't resend |

**Trade-off**: Telegram has no idempotency key, so a request whose outcome is unknown can't be retried safely. FR-010 forbids duplicates, so this design accepts that a crash in the moment between commit and response can lose that one send, which falls short of SC-003 in that rare case. On a normal shutdown the process finishes in-flight sends first, so deployments don't trigger this.

**Overdue note**: If a message goes out more than 1 minute late, a short note with its original time is sent in a separate message just before it, so reminder text is never altered and the 4,096-character limit still holds.

**Plain text**: Messages are sent with no parse mode, so characters such as `*` or `<` in reminder text appear literally.

## Rate limits

**Decision**: A shared limiter holds sends to 25 per second overall and spaces sends to the same chat about 1 second apart. Any 429 response pauses sending for `retry_after`.

**Rationale**: Telegram documents about 30 messages per second for bulk sending and advises about 1 per second per chat. Staying slightly under avoids most 429s.

**Known limit on SC-002**: One user with more than about 60 messages at the same minute would see some go out later than 1 minute, though the FAQ says short bursts may be allowed. This extreme case is accepted, since it's bounded by the 100-message limit and affects only that user.

## Connecting to Telegram

**Decision**: Long polling, with `allowed_updates` set to `message`, `callback_query` and `my_chat_member`.

**Rationale**: It needs no domain, certificate or open port, and only outbound internet access. The update list must name `my_chat_member`, because passing an explicit list excludes anything not on it.

**Alternatives considered**: Webhooks give little benefit at this scale and need public HTTPS.

**Deployment consequence**: Only one process may poll a token at a time, so deployments stop the old container before starting the new one.

## Blocked users

**Decision**: Detect blocks through `my_chat_member` updates, with a 403 on send as a backup.

**To verify**: The API docs say this update fires when a private-chat user blocks or unblocks a bot, but they don't explicitly map statuses. The design treats `kicked` as blocked and `member` as unblocked, and this must be confirmed with a real bot during validation (see [quickstart.md](quickstart.md)).

**Behavior**:
- **While blocked**: The scheduler skips the user, so no sends are attempted.
- **On unblock**: Recurring messages move to their next future send, with no catch-up. An overdue one-time message remains due, so the scheduler sends it once with the note.
- **After 12 calendar months blocked**: The daily job deletes the user, and their messages and delivery records go with them.
- **403 on a claimed one-time message**: It returns to `active` at its original time, so it can still go out after an unblock.

## Delivery record retention

**Decision**: Delete delivery records after 90 days. They store no message text.

**Rationale**: They're only needed to prevent duplicates and diagnose recent failures. Without a limit, 100 daily messages would add about 36,500 rows a year for one user.

## Guided flows

**Decision**: Use aiogram's in-memory flow storage. The final save re-checks ownership, status and the 100-message limit inside its transaction.

**Rationale**: The spec already allows abandoned flows to be discarded, so losing one on restart is acceptable and needs no extra table. Old buttons from before a restart answer with a "no longer available" message.

**Callback data**: Telegram allows only 64 bytes, so buttons carry short forms such as `msg:123:edit`. Every press re-checks that the message belongs to that user (SC-004).

## Languages

**Decision**: Plain English and Ukrainian dictionaries with matching keys, enforced by a test. Bot command descriptions are also registered per language.

**Rationale**: With only two languages and short text, a translation toolchain would be more work than it saves. A user's language is taken from Telegram's `language_code` on first contact (`uk` gives Ukrainian, anything else English) and stored afterwards.

## Hosting and operations

**Decision**: Docker Compose on any small Linux server, with `restart: unless-stopped`, a named volume for the database and a 30-second stop grace period.

**Rationale**: The design only needs Docker, outbound internet and a persistent disk, so it doesn't tie you to a provider. Platforms without persistent disks won't work with SQLite.

**Open**: The provider, and whether backups are copied off the server. The app keeps 7 days of daily backups on the volume, which won't survive losing the server.

**Reliability target**: There's no numeric uptime target. One server restarts automatically after a crash or reboot, and overdue messages go out on recovery (FR-013). Higher availability would need a different storage design.

## Observability and privacy

**Decision**:
- **Logs**: Structured logs go to stdout, using message and user IDs. Reminder text and the bot token are never logged.
- **Health check**: The scheduler updates a heartbeat file on each loop, and the Docker health check reads it to detect a stuck loop.
- **Secrets**: The bot token comes only from the environment and is never committed.
- **Stored data**: Reminder text is stored unencrypted. It's protected by server access and file permissions, and the bot has no need for anything more, since it has to read the text to send it.

## Input limits

**Decision**: Interval from 1 to 3,650 days; dates up to 31.12.2100. Text length is counted in UTF-16 code units, which is the stricter reading of Telegram's limit.

**Rationale**: The spec sets no maximum, but open-ended values risk date overflow and mistyped input. These limits are generous enough not to affect real use.

## Tooling

**Decision**: `uv` for dependencies and running, pytest and pytest-asyncio for tests, Ruff for linting and formatting.

**Rationale**: `uv` is already installed and manages Python itself, which matters because Python isn't otherwise on the development machine's PATH. Time is injected through `clock.py` instead of being patched, so no time-mocking package is needed.
