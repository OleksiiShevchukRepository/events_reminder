# Feature Specification: Telegram Reminder Bot

**Feature Branch**: `main` (no feature branch, by choice)
**Created**: 2026-11-06
**Status**: Draft
**Input**: User description: "Build and deploy a Telegram bot that schedules messages with different recurring frequencies (e.g. once a year, once a week, month, day, custom date). A scheduled message has a message text, a recurring type (only once, every week/month/year/custom date range) and a time when it is sent (e.g. 14:45). The user can update those parameters, see all of their scheduled messages, and create, update and remove them."

## Clarifications

### Session 2026-11-06

- Q: What should a "custom date range" do? → A: The user gives the date of the first message and an interval of N days (e.g. water the plant from 7.11.2026, every 10 days). This spec calls the option "custom interval".
- Q: Do recurring messages have an end date? → A: No. Every recurring type repeats until the user removes the message or switches it to another recurrence type.
- Q: Who can use the bot? → A: Any Telegram user, with a limit of 100 active messages per user.
- Q: Which language should the bot use? → A: English and Ukrainian, chosen from the user's Telegram language setting and changeable in the bot.
- Q: How should users create and edit messages? → A: Guided, step by step: the bot asks for one value at a time, with buttons for choices and typed text for the message, date and time.
- Q: What should a changed custom interval count from? → A: The user must update the date and the interval together, never only one. The next send is on the new date, then every N days.
- Q: Can a date that has passed be set? → A: No, for any recurrence type.
- Q: How do weekly, monthly and yearly messages repeat? → A: Weekly on the start date's weekday (every 7 days), monthly on the same date of the month (the 29th goes out on 28 February unless it is a leap year), yearly on the same date of the year.
- Q: How should users choose their time zone? → A: They don't. The bot uses only Kyiv time, for all users.
- Q: What should happen when a user blocks the bot? → A: Pause sending while blocked and resume on unblock, then delete the user's data after 12 months blocked.
- Q: Can a completed one-time message be updated? → A: No. Completed messages can only be removed, and users create a new message instead.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a scheduled message and receive it (Priority: P1)

A user opens a private chat with the bot and creates a scheduled message by giving its text, how often it repeats, the date it starts on and the time it is sent. The bot confirms what was saved and when it will first be sent. At that time, the bot sends the text to the user in the chat.

**Why this priority**: This is the core value of the product. Without it, the other stories have nothing to act on. On its own it is already a usable reminder bot.

**Independent Test**: Create a one-time message a few minutes in the future, and a weekly message, then confirm that the first arrives at the chosen time and that the second is confirmed with the correct next send date.

**Acceptance Scenarios**:

1. **Given** a user in a private chat with the bot, **When** they create a message with the text "Pay rent", recurrence "only once", a future date and the time 14:45, **Then** the bot confirms the details and sends "Pay rent" at 14:45 on that date.
2. **Given** a saved monthly message starting on 10 March at 09:00, **When** that time arrives, **Then** the bot sends the message and the next send moves to 10 April at 09:00.
3. **Given** a saved weekly message, **When** it has been sent, **Then** the next send moves to the same weekday and time a week later.
4. **Given** a yearly message starting on 5 June, **When** it has been sent, **Then** the next send moves to 5 June of the following year.
5. **Given** a user creating a message, **When** they enter an invalid time (e.g. 25:70), an impossible date (e.g. 31 February) or empty text, **Then** the bot explains the problem and lets them correct that value without restarting.
6. **Given** a user creating a message of any recurrence type, **When** the date and time are in the past, **Then** the bot rejects them and asks for a future date and time.
7. **Given** a custom interval message "Water the plant" starting on 7.11.2026, every 10 days at 14:45, **When** time passes, **Then** the bot sends it at 14:45 on 7.11.2026, 17.11.2026, 27.11.2026, 7.12.2026 and so on.
8. **Given** a daily, weekly, monthly, yearly or custom interval message, **When** the user has not removed it or switched its recurrence type, **Then** it keeps repeating and stays active.
9. **Given** a user creating a custom interval message, **When** they enter an interval of 0 or a non-whole number, **Then** the bot explains the problem and lets them correct that value.
10. **Given** a user anywhere in the world, **When** they enter 14:45 for a message, **Then** the bot shows that the time is Kyiv time and sends the message at 14:45 Kyiv time.
11. **Given** a message set for 14:45, **When** the clocks change in Kyiv, **Then** it is still sent at 14:45 Kyiv time.
12. **Given** a user with 100 active messages, **When** they try to create another, **Then** the bot explains the limit and nothing is saved, and they can create one again after removing an active message.
13. **Given** a first-time user whose Telegram language is Ukrainian, **When** they start the bot, **Then** all bot text appears in Ukrainian; a user with any language other than Ukrainian sees English.
14. **Given** a user with the bot set to English, **When** they change the bot's language to Ukrainian, **Then** all later bot text appears in Ukrainian and the text of their scheduled messages is unchanged.
15. **Given** a user creating a message, **When** they go through the steps, **Then** the bot asks for one value at a time, offers the recurrence types as buttons, and accepts typed text for the message, date (e.g. 7.11.2026) and time (e.g. 14:45).
16. **Given** a user at any step of creating a message, **When** they press Cancel, **Then** nothing is saved.
17. **Given** a monthly message starting on 29 January 2027, **When** it repeats, **Then** it is sent on 28 February 2027 and 29 March 2027, and on 29 February in the leap year 2028.
18. **Given** a weekly message starting on a Wednesday, **When** it repeats, **Then** it is sent every Wednesday, 7 days apart.
19. **Given** a user who has blocked the bot, **When** their messages come due, **Then** no sends are attempted; if they unblock within 12 months, their recurring messages resume at the next scheduled send.
20. **Given** a user who has blocked the bot for 12 continuous months, **When** that period ends, **Then** their data is permanently deleted, and if they return, their list is empty.

---

### User Story 2 - See all scheduled messages (Priority: P2)

A user asks the bot for their scheduled messages and sees each one with a text preview, recurrence, time and next send date, and can open any message to read its full text.

**Why this priority**: Users need to be able to check what is scheduled, and they must be able to find a message before updating or removing it.

**Independent Test**: Create several messages with different recurrences, request the list, and check that all of them appear with correct details.

**Acceptance Scenarios**:

1. **Given** a user with several scheduled messages, **When** they request their list, **Then** they see all of them, ordered by next send date, with a text preview, recurrence, time and next send date.
2. **Given** a user with no scheduled messages, **When** they request their list, **Then** the bot says so and explains how to create one.
3. **Given** two different users with scheduled messages, **When** each requests their list, **Then** each sees only their own messages.
4. **Given** a user with more messages than fit in a single chat message, **When** they request their list, **Then** they can still reach every message.

---

### User Story 3 - Update a scheduled message (Priority: P3)

A user picks one of their scheduled messages and changes its text, recurrence or time. The bot confirms the change and shows the new next send date.

**Why this priority**: Plans change, but a user could work around a missing update by removing and recreating a message.

**Independent Test**: Change the text, the recurrence and the time of an existing message one at a time, and check that the next send uses the new values.

**Acceptance Scenarios**:

1. **Given** a saved message, **When** the user changes its text, **Then** the next send uses the new text and its schedule does not change.
2. **Given** a saved message, **When** the user changes its time from 14:45 to 16:00, **Then** the next send date is recalculated and the old 14:45 send does not happen.
3. **Given** a saved weekly message, **When** the user changes its recurrence to monthly, **Then** the next send date follows the monthly rule and no further weekly sends happen.
4. **Given** a user part-way through an update, **When** they cancel, **Then** the message stays exactly as it was.
5. **Given** a user updating a message, **When** they enter an invalid value, **Then** the bot rejects it and the saved message stays unchanged.
6. **Given** a custom interval message that repeats every 10 days, **When** the user updates it, **Then** the bot asks for both a new date and a new interval, and neither is saved until both are valid.
7. **Given** that update with the new date 25.11.2026 and an interval of 5 days, **When** it is saved, **Then** the next sends are on 25.11.2026, 30.11.2026, 5.12.2026 and so on, and no sends based on the old values happen.
8. **Given** a user updating a message's date, **When** the new date and time are in the past, **Then** the bot rejects them and the saved message stays unchanged.
9. **Given** a completed one-time message in the list, **When** the user selects it, **Then** the bot offers to remove it but not to update it.

---

### User Story 4 - Remove a scheduled message (Priority: P3)

A user picks one of their scheduled messages and removes it after confirming. It is never sent again.

**Why this priority**: Users need a way to stop unwanted reminders, especially recurring ones. It is listed after create, list and update only because it depends on the list.

**Independent Test**: Remove a message that is due in a few minutes and check that it is not sent and no longer appears in the list.

**Acceptance Scenarios**:

1. **Given** a saved message, **When** the user asks to remove it and confirms, **Then** it disappears from their list and is not sent again.
2. **Given** a user asked to confirm a removal, **When** they decline, **Then** the message is kept unchanged.
3. **Given** a list that is out of date because a message was already removed, **When** the user selects that message, **Then** the bot says it no longer exists and nothing else changes.

---

### Edge Cases

- **Short months**: A monthly message set for the 29th, 30th or 31st is sent on the last day of any month without that date, then returns to its original day the following month. For example, the 29th goes out on 28 February, or on 29 February in a leap year.
- **Leap years**: A yearly message set for 29 February is sent on 28 February in non-leap years.
- **Daylight saving time**: Messages keep their Kyiv time across clock changes. If a time does not exist on a given day, the message is sent at the next valid time; if a time occurs twice, it is sent once.
- **Date or time already passed**: A date and time in the past are rejected when entered, for every recurrence type. This includes today's date with a time that has already passed.
- **Time-only update**: Updating only the send time of a recurring message keeps its original start date, and the next send is the next date on its schedule at the new time. Updating the time of a one-time message requires the resulting date and time to be in the future.
- **Bot unavailable at send time**: After recovery, each overdue message is sent once with a note of its original time. A recurring message that missed several sends is sent only once, then resumes its schedule.
- **User has blocked the bot**: Sending pauses while the bot is blocked. On unblock, recurring messages resume at their next scheduled send without catching up, and a one-time message that came due during the block is sent once with a note of its original time. After 12 months blocked, the user's data is deleted, and returning later starts from nothing.
- **Temporary delivery failure**: Sending is retried until Telegram accepts it or rejects it permanently, including across restarts. After a long outage, a message is sent once with a note of its original time, and a recurring message that missed several sends is sent only once.
- **Editing at send time**: If a message is updated or removed at the moment it is due, it is either sent in its previous form or handled under the new values, but never both.
- **Maximum length**: Text longer than Telegram's single-message limit (4,096 characters) is rejected with a clear explanation.
- **Abandoned input**: If a user stops part-way through creating or updating a message, nothing is saved or changed, and they can start again at any time.
- **Unsupported input**: Photos, stickers and other non-text content sent as message text are rejected with an explanation.

## Requirements *(mandatory)*

### Functional Requirements

**Creating and scheduling**

- **FR-001**: Users MUST be able to create a scheduled message in a private chat with the bot.
- **FR-001a**: Creating and updating MUST be guided step by step, with the bot asking for one value at a time. Choices such as recurrence type, and selecting a message to update or remove, MUST use buttons. Message text, dates (day.month.year, e.g. 7.11.2026), times (24-hour, e.g. 14:45) and intervals MUST be typed. Every step MUST offer a way to cancel.
- **FR-002**: Each scheduled message MUST have message text, a recurrence type, a start date and a send time given in hours and minutes (e.g. 14:45).
- **FR-003**: The system MUST support these recurrence types: only once, every day, every week, every month, every year and custom interval (every N days).
- **FR-004**: For the custom interval recurrence, users MUST provide an interval of N days, where N is a whole number from 1 to 3,650. The system MUST send on the start date and every N days after it.
- **FR-005**: The system MUST validate all input and explain any rejected value, letting the user correct it without re-entering valid values.
- **FR-006**: The system MUST confirm every saved message, including its next send date and time.
- **FR-005a**: The system MUST reject any entered date and time that is in the past, for every recurrence type, both when creating and when updating. Dates after 31.12.2100 MUST also be rejected.
- **FR-007**: Weekly messages MUST repeat every 7 days on the weekday of their start date. Monthly messages MUST repeat on the same date of the month as their start date. Yearly messages MUST repeat on the same date of the year as their start date.
- **FR-007a**: Recurring messages (every day, week, month, year and custom interval) MUST NOT have an end date. They MUST repeat until the user removes the message or switches it to another recurrence type.

**Delivery**

- **FR-008**: The system MUST send each message to the chat of the user who created it at its scheduled time in Kyiv time.
- **FR-009**: The system MUST calculate the next send date after each send of a recurring message, following the Edge Cases rules for short months, leap years and daylight saving time.
- **FR-010**: The system MUST NOT send a message more than once for the same scheduled send. The one accepted risk is retrying after a gateway error from Telegram, which usually means the message was never received but can't prove it.
- **FR-011**: One-time messages MUST NOT be sent again once they have been sent. They MUST stay visible in the list marked as completed, or as not delivered if the send failed permanently, until the user removes them, and MUST NOT be updatable.
- **FR-012**: Scheduled messages MUST survive restarts and redeployments of the bot.
- **FR-013**: After downtime, the system MUST send each overdue message once, with a note of its original time, and resume its schedule.
- **FR-013a**: The system MUST pause sending to a user who has blocked the bot and resume when they unblock it, following the Edge Cases rule. After 12 continuous months blocked, it MUST permanently delete that user's record, scheduled messages and delivery records.

**Viewing**

- **FR-014**: Users MUST be able to see all of their scheduled messages with a text preview, recurrence, send time, next send date and status, and open any message to read its full text.
- **FR-015**: The list MUST show active messages first, ordered by next send date, and every message MUST be reachable however many there are.

**Updating and removing**

- **FR-016**: Users MUST be able to update the text, recurrence type, start date and send time of any of their active messages, and the interval of custom interval messages.
- **FR-016a**: For custom interval messages, the date and the interval MUST be updated together, never only one of them. After the update, the next send MUST be on the new date, then every N days. Switching an active message to custom interval or "only once" MUST also ask for a new date.
- **FR-017**: After a recurrence or time update, the system MUST recalculate the next send date and MUST NOT make any send based on the old values.
- **FR-018**: Users MUST be able to cancel an update before it is saved, leaving the message unchanged.
- **FR-019**: Users MUST be able to remove any of their messages after an explicit confirmation. A removed message MUST NOT be sent again.

**Users and access**

- **FR-020**: Any Telegram user who starts the bot MUST be able to use it, without separate registration.
- **FR-020a**: The system MUST limit each user to 100 active messages and explain the limit when it is reached. Completed messages MUST NOT count towards it.
- **FR-021**: Users MUST only be able to see, update or remove their own messages.
- **FR-022**: All dates and times MUST use Kyiv time for all users, including the check for past dates. Users MUST NOT be asked to choose a time zone. The bot MUST state that times are Kyiv time when asking for a time and when confirming a message.
- **FR-023**: The bot MUST explain its available actions when started and on request.
- **FR-023a**: All bot text MUST be available in English and Ukrainian. The initial language MUST come from the user's Telegram language setting, using Ukrainian for Ukrainian and English for anything else, and users MUST be able to change it in the bot. The system MUST NOT translate the text of scheduled messages.

**Availability**

- **FR-024**: The bot MUST be deployed to an always-on environment, so users can reach it and messages are sent without any user or operator action.

### Key Entities

- **User**: A person using the bot, identified by their Telegram account. Has a private chat with the bot, a language and, while the bot is blocked, the date the block began.
- **Scheduled Message**: A reminder owned by one user. Has text, recurrence type, start date, send time, interval in days (custom interval only), next send date and status (active or completed).
- **Delivery Record**: One attempted send of a scheduled message. Has the scheduled time, the actual time and the outcome. Used to prevent duplicate sends and to diagnose failures.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can create a scheduled message in under 1 minute without outside help.
- **SC-002**: At least 99% of messages are delivered within 1 minute of their scheduled time while the bot is running normally.
- **SC-003**: No message is lost because of a restart or redeployment: all of them are delivered on schedule or, if overdue, once after recovery. The one exception is a hard crash at the moment of sending, when the outcome can't be known. That send isn't repeated, because duplicates are forbidden (FR-010).
- **SC-004**: No user can ever see or change another user's messages.
- **SC-005**: Over a full year of test dates, weekly, monthly, yearly and custom interval messages are always scheduled for the correct date, including short months, leap years and clock changes.
- **SC-006**: A user can see their list, or finish an update or removal, in under 30 seconds.
- **SC-007**: The bot responds to at least 95% of user actions within 2 seconds.

## Assumptions

- **Start date added**: The request lists text, recurrence and time, but one-time, weekly, monthly and yearly messages also need a date to know when to send, so a start date is a required parameter.
- **Daily recurrence included**: The request's example frequencies mention "day", though its parameter list doesn't, so "every day" is included.
- **"Custom date"**: A single custom date is covered by "only once" with a chosen date.
- **Multiple users**: The phrase "his scheduled messages" implies each user has their own set, so the bot is open to any Telegram user.
- **Private chats only**: Group and channel support is out of scope. Messages go only to the user who created them.
- **Text only**: Scheduled messages contain plain text. Attachments and rich formatting are out of scope.
- **Time zone**: All times are Kyiv time and follow Kyiv's official clock changes. Users elsewhere convert times themselves.
- **Removal is permanent**: Removed messages cannot be restored.
- **Backups**: Deleted data can remain in daily backups for up to 7 days.
- **Hosting**: The specific hosting environment is chosen before deployment. An operator supplies the bot's Telegram token and hosting account.
- **No charges**: This version has no paid tiers.

## Out of Scope

- Group chats, channels, and sending to other people
- Attachments and rich text
- Choosing a time zone other than Kyiv
- Snooze and acknowledgement of reminders
- Web or mobile interfaces other than Telegram
- Importing from or syncing with external calendars
