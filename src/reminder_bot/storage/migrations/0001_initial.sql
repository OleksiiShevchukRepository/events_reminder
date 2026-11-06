CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    language TEXT NOT NULL CHECK (language IN ('en', 'uk')),
    blocked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE scheduled_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    recurrence TEXT NOT NULL
        CHECK (recurrence IN ('once', 'daily', 'weekly', 'monthly', 'yearly', 'interval')),
    start_date TEXT NOT NULL,
    send_time TEXT NOT NULL,
    interval_days INTEGER,
    next_send_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_messages_due ON scheduled_messages (status, next_send_at);
CREATE INDEX idx_messages_user ON scheduled_messages (user_id, status, next_send_at);

CREATE TABLE deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES scheduled_messages (id) ON DELETE CASCADE,
    scheduled_at TEXT NOT NULL,
    sent_at TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('sending', 'retrying', 'sent', 'failed', 'unknown', 'blocked')),
    next_attempt_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL
);

-- Prevents a second send of the same scheduled time (FR-010). A send returned by
-- a block is excluded, so a one-time message can be claimed again after an unblock.
CREATE UNIQUE INDEX idx_deliveries_once_per_send
    ON deliveries (message_id, scheduled_at)
    WHERE status != 'blocked';

CREATE INDEX idx_deliveries_retry ON deliveries (status, next_attempt_at);
CREATE INDEX idx_deliveries_created ON deliveries (created_at);
