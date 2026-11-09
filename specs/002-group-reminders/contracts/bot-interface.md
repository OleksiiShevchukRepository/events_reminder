# Contract: Bot Interface in Groups

What changes from the [001 bot interface](../../001-telegram-reminder-bot/contracts/bot-interface.md). Anything not listed here works the same in groups as in private chats. All new text exists in English and Ukrainian.

## Joining a group

When the bot is added to a group, or added back, it posts a welcome message in the group's language (FR-112). It explains:
- Reminders made here are posted here for everyone, in the General topic if the group has topics.
- Any member can create, change and remove them, with `/new` and `/list`.
- Answer the bot's questions by replying to them.
- Making the bot an admin allowed to delete messages keeps the chat tidy and lets members answer without replying.

## Commands in groups

| Command | Behavior |
|---|---|
| `/start`, `/help` | The group version of help, with the main menu |
| `/new` | Starts a create flow for the member who sent it |
| `/list` | Shows the group's reminders |
| `/language` | Changes the group's language, for any member |
| `/cancel` | Ends the sender's own flow only |

`/command@BotName` works the same. Commands addressed to other bots, and commands this bot doesn't know, are ignored. The bot never replies to ordinary group messages (FR-113).

Commands are registered for private chats and for all group chats.

## Flows in groups

The steps and their order are the same as in private chats.

- **Questions**: Each question starts with a mention of the member, for example "Oleksii, send the text of your reminder.", and opens the reply box only for them (FR-104).
- **Answers**: Accepted only from the member who started the flow. Where the bot isn't an admin, the member must reply to the question. Where it is, they may also type normally (FR-104a).
- **Cancelling**: Questions that need a typed answer open the reply box, which can't be combined with buttons, so they end with "Send /cancel to stop" instead of a Cancel button. Questions answered with buttons, such as the recurrence choice, keep the Cancel button.
- **Anonymous admins**: `/new`, `/language`, Edit and Remove get a request to turn off "Remain anonymous", and nothing starts. `/list` and `/help` work.
- **Buttons**: Buttons in a flow's questions, such as recurrence choices and Cancel, work only for the member who started it. Anyone else gets a short "This isn't your request" notice, and the flow doesn't change (FR-105).
- **Topics**: Questions and replies stay in the topic where the member started (FR-114).

## Flow clean-up, in groups and private chats

When a create or update flow ends, by saving, Cancel, `/cancel` or another command, the bot deletes:
- the command or button press message that started it, if it was a member's message
- every question and error reply the bot sent in the flow
- every answer the member sent in the flow

Then it sends the final message, which stays (FR-119). In a group where the bot can't delete members' messages, members' messages stay and the bot's are still deleted (FR-120). Remove confirmations aren't flows; their prompt is edited into the result, as now.

## List and reminder screens in groups

- `/list` shows the group's reminders, with the same paging (10 per page) as in private chats (FR-107).
- Any current member can page, open a reminder, and use Edit and Remove. Each press first checks that the presser is still a member; anyone else gets "This is no longer available" (FR-110a).
- A group reminder's screen adds two lines (FR-121):

```text
Created by: Anna
Last changed by: Oleksii
```

The second line is shown only after a change.

## Confirmations in groups

Confirmations name the member (FR-122). Private chats keep the 001 wording.

| Event | Group confirmation |
|---|---|
| Saved | "Saved by Anna." followed by the usual summary |
| Updated | "Updated by Oleksii." followed by the usual summary |
| Removed | "Removed by Oleksii:" followed by the removed text |

## Delivered reminders

Posted in the group's General topic as plain text, with no names, and with the overdue note when late, as in private chats.

## Callback data

Unchanged. Reminder IDs in callback data are always looked up within the chat the button's message is in.

## Telegram updates

| Update | New use |
|---|---|
| `message` | Group commands and flow answers. Service messages with `migrate_to_chat_id` trigger the supergroup move |
| `callback_query` | Group button presses, after a membership check |
| `my_chat_member` | Bot added to, removed from, or restricted in a group |

## Telegram API calls

| Method | New use |
|---|---|
| `deleteMessages` | Flow clean-up |
| `getChatMember` | Membership check on group button presses |
| `setMyCommands` | Adds the group chat command scope |
| `sendMessage` | Adds `message_thread_id` for topics, and `ForceReply` with a text mention for group questions |
