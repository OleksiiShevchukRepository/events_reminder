-- Reminders belong to a chat: a private chat, whose ID is the person's ID, or a group
-- (specs/002-group-reminders/data-model.md). Existing rows keep their IDs and meaning.

ALTER TABLE users RENAME TO chats;
ALTER TABLE chats RENAME COLUMN blocked_at TO unreachable_at;
ALTER TABLE chats ADD COLUMN kind TEXT NOT NULL DEFAULT 'private'
    CHECK (kind IN ('private', 'group'));

ALTER TABLE scheduled_messages RENAME COLUMN user_id TO chat_id;
-- Display names of the members who created and last changed a group reminder.
ALTER TABLE scheduled_messages ADD COLUMN created_by_name TEXT;
ALTER TABLE scheduled_messages ADD COLUMN changed_by_name TEXT;

DROP INDEX idx_messages_user;
CREATE INDEX idx_messages_chat ON scheduled_messages (chat_id, status, next_send_at);
