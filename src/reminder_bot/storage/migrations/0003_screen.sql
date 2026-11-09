-- The bot's current screen in a private chat: its latest menu, list or confirmation.
-- Showing a new screen deletes the previous one (002 FR-124). Comma-separated message IDs,
-- because a reminder with very long text is shown as two messages.
ALTER TABLE chats ADD COLUMN screen_message_ids TEXT;
