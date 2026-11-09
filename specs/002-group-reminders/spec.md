# Feature Specification: Group Reminders

**Feature Branch**: `main` (no feature branch, by choice)

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "add new feature that allows group usage of the bot"

This feature extends the reminder bot defined in [001-telegram-reminder-bot](../001-telegram-reminder-bot/spec.md). Everything that spec says about reminders, such as recurrence rules, Kyiv time, validation, delivery and the guided steps, applies to group reminders too unless this spec says otherwise. Private chats keep working exactly as they do now.

## Clarifications

### Session 2026-11-09

- Q: Who can change and remove a group's reminders? → A: Any member of the group.
- Q: Where should reminders go in groups with topics? → A: Always the group's main (General) topic, wherever they were created.
- Q: What happens to the bot's questions and members' answers after a flow? → A: When a flow ends, the bot deletes its questions and the member's answers, leaving only the final result. In groups, deleting members' answers needs the bot to be an admin allowed to delete messages; without that, only the bot's own questions are deleted. The same clean-up applies in private chats.
- Q: Should the group see who created or changed a reminder? → A: Yes. A group reminder's screen shows who created it and who last changed it, and each confirmation in the group names the member who saved, updated or removed it. Delivered reminders don't show names.
- Q: Should a private chat keep the bot's older menus, lists and confirmations? → A: No. A private chat keeps only the bot's current screen: showing a new menu, list, help or result deletes the previous one and the command the person typed. Delivered reminders are kept. Groups are unchanged.
- Q: Should groups clear older screens too? → A: Yes, the same as private chats, including the confirmations that name a member. A group has one screen, shared by all members.
- Q: How do members answer the bot's questions in a group? → A: By replying to the bot's question, which works in every group. When the bot is an admin, the member who started the flow can also type their answer without replying.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a group reminder and receive it in the group (Priority: P1)

A member of a Telegram group that the bot has been added to creates a reminder in that group, using the same guided steps as in a private chat. At the chosen time, the bot posts the reminder text in the group, where every member sees it.

**Why this priority**: This is the whole point of the feature. On its own it lets a family, team or flat share reminders such as "Bins go out tonight" or "Stand-up in 10 minutes".

**Independent Test**: Add the bot to a test group, create a one-time reminder a few minutes ahead from one member's account, and check that it appears in the group at that time and not in anyone's private chat.

**Acceptance Scenarios**:

1. **Given** a group with the bot in it, **When** a member creates a reminder "Bins go out tonight", every Tuesday at 19:00, **Then** the bot confirms it in the group and posts "Bins go out tonight" in the group every Tuesday at 19:00 Kyiv time.
2. **Given** a member creating a group reminder, **When** they go through the steps, **Then** the bot asks the same questions in the same order as in a private chat, and the member can answer them without the group changing any of its settings.
3. **Given** two members creating group reminders at the same time, **When** they answer the bot's questions, **Then** each member's answers go only into their own reminder.
4. **Given** a member creating a group reminder, **When** another member presses a button or answers a question in that member's flow, **Then** only that person sees a short notice that it isn't their request, and the flow is unchanged.
5. **Given** a group reminder that is due, **When** it is sent, **Then** it goes only to the group, not to the private chat of the member who created it.
6. **Given** a group with 100 active reminders, **When** a member tries to create another, **Then** the bot explains the limit and nothing is saved.
7. **Given** a member creating a group reminder, **When** they press Cancel or stop answering, **Then** nothing is saved.
8. **Given** a group where the bot is an admin allowed to delete messages, **When** a member finishes creating a reminder, **Then** the bot's questions, any error replies and the member's answers are deleted, and only the confirmation stays in the chat.
9. **Given** a group where the bot isn't allowed to delete messages, **When** a member finishes creating a reminder, **Then** the bot deletes only its own questions and error replies, and the member's answers stay.
10. **Given** a person creating a reminder in their private chat, **When** they finish or cancel, **Then** the bot's questions and their answers are deleted, leaving only the confirmation or the "Cancelled" message.
11. **Given** a group where the bot isn't an admin, **When** the member answers a question by replying to it, **Then** the bot accepts the answer; if they type without replying, the bot doesn't see it and the question stays open.
12. **Given** a group where the bot is an admin, **When** the member who started the flow types "14:45" without replying, **Then** the bot accepts it, and the same message from another member is ignored.

---

### User Story 2 - See a group's reminders (Priority: P2)

A member asks the bot for the reminders in the group and sees the group's reminders, in the same list format as in a private chat.

**Why this priority**: Members need to know what is scheduled for the group, and the list is how they find a reminder before changing or removing it.

**Independent Test**: Create several group reminders and some private ones, then request the list in the group and in a private chat, and check that each shows only its own reminders.

**Acceptance Scenarios**:

1. **Given** a group with several reminders, **When** a member requests the list in the group, **Then** they see all of the group's reminders, ordered by next send date, with paging as in a private chat.
2. **Given** a member who has private reminders and belongs to a group with reminders, **When** they request the list in their private chat, **Then** they see only their private reminders.
3. **Given** two groups that both have the bot, **When** the list is requested in each, **Then** each shows only its own group's reminders.
4. **Given** a group with no reminders, **When** a member requests the list, **Then** the bot says so and offers to create one.

---

### User Story 3 - Change or remove a group's reminders (Priority: P3)

Any member updates or removes one of the group's reminders, using the same steps as in a private chat.

**Why this priority**: Group plans change too, but a group can work around a missing update by removing and recreating a reminder. Removal matters more than update, so that unwanted reminders can be stopped.

**Independent Test**: From one member's account, create a group reminder, then from a second member's account change its time and remove another reminder, and check the group's list reflects both changes.

**Acceptance Scenarios**:

1. **Given** a group reminder, **When** any member changes its text, recurrence, date or time, **Then** the next send uses the new values, as in a private chat.
2. **Given** a group reminder created by one member, **When** another member removes it after confirming, **Then** it is never sent again and disappears from the group's list.
3. **Given** someone who isn't a member of the group, **When** they press an old button for one of the group's reminders, **Then** nothing changes.
4. **Given** a group reminder created by Anna and later changed by Oleksii, **When** a member opens it, **Then** its screen shows "Created by Anna" and "Last changed by Oleksii".
5. **Given** a member who removes a group reminder, **When** the removal is confirmed, **Then** the confirmation left in the group names that member, for example "Removed by Oleksii", along with the reminder's text.

---

### User Story 4 - Group language (Priority: P3)

The bot uses one language for each group, which members can change.

**Why this priority**: Groups often share one language, and messages from the bot in the group are seen by everyone.

**Independent Test**: Add the bot to a group from an account set to Ukrainian, check the bot replies in Ukrainian, then change the group's language to English and check all later bot text in the group is English.

**Acceptance Scenarios**:

1. **Given** the bot was just added to a group, **When** it first speaks in the group, **Then** it uses Ukrainian if the member who added it or first used it has Telegram set to Ukrainian, and English otherwise.
2. **Given** a group whose bot language is English, **When** any member changes it to Ukrainian, **Then** all later bot text in that group is Ukrainian, and members' private chats keep their own languages.

---

### Edge Cases

- **Bot removed from a group**: Sending to that group pauses. If the bot is added back within 12 months, the group's recurring reminders resume at their next send without catching up, and a one-time reminder that came due meanwhile is sent once with a note of its original time. After 12 continuous months without the bot, the group's reminders and records are permanently deleted.
- **Bot can't post in the group**: If the group stops the bot from sending messages but keeps it as a member, the group is treated as if the bot had been removed, and sending resumes once the bot can post again.
- **Group upgraded by Telegram**: When Telegram upgrades a group to a supergroup, which gives it a new identity, its reminders, language and settings carry over and keep being sent.
- **Creator leaves the group**: A group reminder belongs to the group, so it keeps being sent after the member who created it leaves.
- **Many reminders at the same minute**: Telegram limits how fast a bot can post in one group. Reminders due together in one group are sent in order of their time, and all are sent, even if some arrive a little later than the minute they were due.
- **Command meant for another bot**: In a group with several bots, the bot responds only to its own commands, including commands addressed to it by name.
- **Ordinary group conversation**: The bot doesn't react to, store or read messages that aren't meant for it.
- **Group deleted**: A group that no longer exists is handled like a group the bot was removed from.
- **Channels**: Adding the bot to a channel does nothing; it doesn't save anything for the channel.
- **Flow that never ends**: If a flow is abandoned and never finished or cancelled, or the bot restarts in the middle of it, its messages may stay in the chat.
- **Old messages**: Telegram only lets bots delete messages up to 48 hours old. Messages from a flow that took longer than that stay in the chat.
- **Cancelling in a group**: Questions that open the reply box can't also show buttons, so they tell the member to send `/cancel`.
- **Anonymous admins**: An admin posting anonymously can't create, change or remove reminders. The bot asks them to turn off "Remain anonymous" first. They can still use `/list` and `/help`.
- **Chatting during a flow**: Where the bot is an admin, any ordinary message from the member who started a flow is taken as their answer to the current question, so a stray message may become the reminder text or get an error reply.
- **Clean-up fails**: If a message can't be deleted, for example because a member already deleted it or the bot lost its admin rights, the bot skips it and the reminder is still saved or cancelled as normal.

## Requirements *(mandatory)*

### Functional Requirements

**Group reminders**

- **FR-101**: Members of a group that the bot has been added to MUST be able to create reminders for that group.
- **FR-102**: A group reminder MUST belong to the group, not to the member who created it, and MUST be sent only to that group.
- **FR-103**: Group reminders MUST follow all of the reminder rules in the 001 spec: the same recurrence types and repeat rules, Kyiv time, validation, past-date rejection, confirmations, delivery, overdue notes, duplicate prevention and survival across restarts.
- **FR-104**: Creating and updating a group reminder MUST use the same guided steps, in the same order, as in a private chat. Members MUST be able to answer the bot's questions in the group by replying to them, without the group changing its settings. Each question that needs a typed answer MUST open the reply box for the member who started the flow and ask them to reply. In groups, such a question MUST say that `/cancel` stops the flow, instead of showing a Cancel button. Questions answered with buttons, such as the recurrence choice, MUST keep the Cancel button.
- **FR-104a**: When the bot is an admin of the group, the member who started a flow MUST also be able to type an answer without replying. Plain messages from other members MUST still be ignored.
- **FR-105**: Each member's flow in a group MUST be separate. Only the member who started a flow can answer its questions or press its buttons; input from other members MUST NOT change it.
- **FR-106**: The system MUST limit each group to 100 active reminders, counted separately from every member's private limit. Completed reminders MUST NOT count towards it.

**Viewing**

- **FR-107**: The list requested in a group MUST show only that group's reminders. The list requested in a private chat MUST show only that person's private reminders.
- **FR-108**: Any member of a group MUST be able to see the group's list and open any of its reminders.

**Permissions**

- **FR-109**: Any member of a group MUST be able to create, update and remove any of the group's reminders, whoever created them.
- **FR-110**: Any member of a group MUST be able to change the group's language.
- **FR-110a**: Only current members of a group MUST be able to act on its reminders. Anyone else MUST NOT be able to see or change them, including through old buttons.

**Group language and help**

- **FR-111**: Each group MUST have one bot language, English or Ukrainian. It MUST start from the Telegram language of the member who added the bot or first used it, using Ukrainian for Ukrainian and English for anything else, and any member MUST be able to change it.
- **FR-112**: When the bot is added to a group, including when it's added back after being removed, it MUST post a short message explaining what it does and how to start, in the group's language. The message MUST mention that making the bot an admin allowed to delete messages keeps the chat tidy (FR-119).
- **FR-113**: In a group, the bot MUST respond only to its own commands and to answers in an active flow, and MUST NOT store, log or react to other group messages, including the messages it can see as an admin.

**Topics**

- **FR-114**: In groups divided into topics, reminders MUST always be sent to the group's main (General) topic, whichever topic they were created in. The bot's questions and replies while creating, listing, updating or removing MUST appear in the topic where the member is working.

**Lifecycle**

- **FR-115**: The system MUST pause sending to a group the bot was removed from or can't post in, and resume when it can post again, following the Edge Cases rule. After 12 continuous months, it MUST permanently delete the group's record, reminders and delivery records.
- **FR-116**: When Telegram gives a group a new identity by upgrading it, the system MUST move the group's reminders and settings to it with nothing lost or sent twice.
- **FR-117**: Channels MUST NOT be supported. The bot MUST NOT store anything for a channel it's added to.

**Who did what**

- **FR-121**: Each group reminder MUST record which member created it and which member last changed it. Its screen in the group MUST show both.
- **FR-122**: Every confirmation in a group, until the next screen replaces it (FR-124), of a saved, updated or removed reminder MUST name the member who did it. A removal confirmation MUST also include the removed reminder's text, so the group knows what was removed.
- **FR-123**: Members MUST be named by their Telegram display name at the time of the action. Delivered reminders and private chats MUST NOT show names.

**Chat clean-up**

- **FR-119**: When a create or update flow ends, whether saved, cancelled or ended by another command, the bot MUST delete the messages that flow produced: its own questions and error replies, and the member's answers. Only the final message, such as the confirmation or "Cancelled", MUST remain. This applies in both groups and private chats.
- **FR-120**: In a group where the bot isn't allowed to delete other members' messages, it MUST still delete its own flow messages and leave members' answers. A message that can't be deleted MUST NOT stop the flow from saving or cancelling.
- **FR-124**: In every chat, private or group, the bot MUST keep only its current screen: its latest menu, list, help, welcome, reminder screen or result, such as "Saved." or "Removed by Anna:". Showing a new screen MUST delete the previous one and the command or text that asked for it. A group has one screen, shared by all its members and topics. Deleting a member's command in a group needs the bot to be an admin allowed to delete messages; without that, the command stays and the bot's own messages are still deleted. Pressing a button on an older message makes that message the current screen. Delivered reminders MUST NOT be deleted. This MUST still work after a restart.

**Private chats**

- **FR-118**: Private chat behavior MUST NOT change, except for the clean-up in FR-119. Group reminders MUST NOT appear in, or count towards the limit of, anyone's private chat.

### Key Entities

- **Group**: A Telegram group the bot has been added to. Has a language, whether the bot can currently post there, and, while it can't, the date that began. Owns its reminders.
- **Reminder** (the 001 spec's Scheduled Message): Now belongs either to one person's private chat or to one group. Group reminders also record the member who created them and the member who last changed them, by display name.
- **Delivery Record**: Unchanged from the 001 spec.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-101**: A group member who has used the bot privately can create a group reminder in under 1 minute without help.
- **SC-102**: At least 99% of group reminders are posted within 1 minute of their scheduled time while the bot is running normally, when a group has no more than 15 reminders due in the same minute.
- **SC-103**: No group's reminders ever appear in, or are changeable from, another group or anyone's private chat, and no private reminder ever appears in a group.
- **SC-104**: Nobody outside a group is ever able to see, change or remove that group's reminders.
- **SC-105**: With two members creating reminders in the same group at once, their answers are never mixed up.
- **SC-106**: All existing private chat checks from the 001 spec still pass, apart from the added clean-up.
- **SC-107**: After a reminder is created where the bot is allowed to delete messages, only one message from that flow, the confirmation, remains in the chat.
- **SC-108**: However many actions people take in a chat, at most one screen from the bot remains, apart from delivered reminders and messages older than Telegram's 48-hour deletion limit.

## Assumptions

- **Groups and supergroups**: "Group" means both ordinary groups and supergroups. Channels are out of scope.
- **Separate lists**: Private and group reminders are kept apart. A private `/list` shows only private reminders, even for members of groups with reminders.
- **Same limits and rules**: Groups use the same limits as people: 100 active reminders, the same date range, and the same interval range.
- **Answering in a group**: Replying to the bot's question works with Telegram's default group settings, so no group needs to change anything. Typing without replying works only when the bot is an admin, because only then does Telegram show the bot ordinary group messages.
- **No mentions**: Reminders are posted as plain text. Mentioning or notifying specific members is out of scope.
- **Same retention**: The 12-month pause before deletion, 90-day delivery records and 7-day backups from the 001 spec also apply to groups.
- **Shared control**: Any member can change or remove any group reminder, so groups rely on trust between members. Telegram's own group settings decide who is a member.
- **Making the bot an admin**: Groups decide for themselves whether to give the bot permission to delete messages. The bot's message on joining a group mentions that this keeps the chat tidy, but doesn't require it.
- **Adding the bot**: Anyone allowed by the group's own Telegram settings can add the bot. The bot doesn't restrict which groups it joins.

## Out of Scope

- Channels
- Sending a reminder created in a private chat to a group, or the other way round
- Mentioning, assigning or notifying specific members
- Per-member settings inside a group, such as different languages for different members
- Limiting which groups may use the bot
