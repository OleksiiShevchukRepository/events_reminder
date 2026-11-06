# Contract: Runtime Configuration

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `BOT_TOKEN` | Yes | | Token from BotFather. Must never be logged or committed. |
| `DATABASE_PATH` | No | `/data/reminders.db` | Database file, on a persistent volume |
| `BACKUP_DIR` | No | `/data/backups` | Daily backups, 7 days kept |
| `LOG_LEVEL` | No | `INFO` | Log detail |

The process exits with a clear error at startup if `BOT_TOKEN` is missing or the database location can't be written.

The time zone is fixed at `Europe/Kyiv` in code, not configured (FR-022). The container's own time zone doesn't affect behavior.

## Container behavior

| Behavior | Requirement |
|---|---|
| Startup | Applies migrations, marks leftover `sending` records as `unknown`, then starts polling and the scheduler, which resumes `retrying` records |
| Shutdown (SIGTERM) | Stops taking new work and finishes sends already in flight, within 30 seconds; `retrying` sends resume after restart |
| Restart policy | `unless-stopped` |
| Instances | Exactly one per bot token, because Telegram allows only one poller |
| Network | Outbound HTTPS to `api.telegram.org`; no open ports |
| Health check | Heartbeat file updated by the scheduler loop; unhealthy after 60 seconds without an update |
| Volume | `/data` must persist across deployments |

## Logs

Written to stdout, one event per line, with message and user IDs where relevant. Logs must never contain the bot token or reminder text.
