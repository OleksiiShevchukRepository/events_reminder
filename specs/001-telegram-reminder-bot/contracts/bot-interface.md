# Contract: Bot Interface

This is what users see and what the bot exchanges with Telegram. All visible text exists in English and Ukrainian (FR-023a). Exact wording lives in the translation files.

## Commands

| Command | Behavior | Spec |
|---|---|---|
| `/start` | Registers the user if new, sets their language on first contact, explains the actions and shows the main menu | FR-020, FR-023 |
| `/new` | Starts the create flow | FR-001 |
| `/list` | Shows the user's messages | FR-014 |
| `/language` | Offers English or Ukrainian as buttons | FR-023a |
| `/help` | Explains the available actions and that times are Kyiv time | FR-023 |
| `/cancel` | Ends any flow in progress with no changes | FR-001a, FR-018 |

The main menu offers **New message**, **My messages** and **Language** as buttons.

A command sent during a flow ends that flow without saving and runs the command, so nobody gets stuck. To use text beginning with `/` as a reminder, only recognized commands are treated this way.

## Create flow

Each step offers **Cancel**. An invalid value repeats only that step with an explanation (FR-005).

| Step | Input | Rejected when |
|---|---|---|
| 0. Limit check | None | The user already has 100 active messages (flow doesn't start) |
| 1. Recurrence ("How often should it be sent?") | Buttons: Only once, Every day, Every week, Every month, Every year, Every N days | |
| 2. Text | Typed | Blank, too long, or not text (photo, sticker and so on) |
| 3. Interval (Every N days only) | Typed whole number | Not a whole number from 1 to 3,650 |
| 4. Date | Typed, e.g. `7.11.2026` | Not a real date, wrong format, after 31.12.2100, or before today in Kyiv |
| 5. Time | Typed, e.g. `14:45`, with a "Kyiv time" label | Not a valid time, or the date and time together are in the past |

**On save**, the bot confirms the text, recurrence, Kyiv time and next send (FR-006, FR-022). The limit is checked again in the save transaction.

## List

- Active messages come first, by next send date, followed by completed ones (FR-015).
- Pages show 5 messages, with **Previous** and **Next** buttons, so every message is reachable.
- Each entry shows a text preview, recurrence, time, next send date and status (FR-014). Selecting it opens a screen with the full text.
- A one-time message being sent shows "Sending" as its next send date. A completed message whose send failed permanently shows "Not delivered" as its status (FR-011).
- An empty list says so and offers **New message**.

## Message screen

| Message status | Buttons |
|---|---|
| Active | Edit text, Edit recurrence, Edit date, Edit time, Remove, Back |
| Active, `interval` | Edit text, Edit recurrence, Edit date and interval, Edit time, Remove, Back |
| Completed | Remove, Back (FR-011) |

## Update flows

Every flow shows **Cancel**, validates like the create flow and saves nothing until its last step. It then confirms the new values and next send.

| Action | Asks for |
|---|---|
| Edit text | New text |
| Edit time | New time |
| Edit date | New date |
| Edit date and interval | New date, then new interval; both are required (FR-016a) |
| Edit recurrence to daily, weekly, monthly or yearly | Only the choice |
| Edit recurrence to Only once | Choice, then new date, then new time if the existing time would be in the past |
| Edit recurrence to Every N days | Choice, then new interval, then new date, with the same time rule |

## Remove flow

Pressing **Remove** shows the text with **Yes, remove** and **Keep** buttons (FR-019). Removal is permanent.

## Stale or unauthorized buttons

Each button press re-checks the message at the moment it's pressed. The bot answers "no longer available" and changes nothing when:
- The message was removed or doesn't belong to this user (SC-004). Both give the same answer, so the bot doesn't reveal that another user's message exists.
- An active-only action is used on a completed message.
- The flow it belonged to has ended, for example after a restart.

## Delivered messages

- **On time**: Only the message text, sent as plain text with no parse mode.
- **More than 1 minute late**: A separate note with the original date and time in Kyiv time, then the text (FR-013).

## Callback data

Must fit in 64 bytes. It contains only short action names and numeric IDs, never message text:

```text
menu:new | menu:list | menu:language
rec:<recurrence>
msg:<id>:open | msg:<id>:edit_text | msg:<id>:edit_rec | msg:<id>:edit_date | msg:<id>:edit_time | msg:<id>:remove | msg:<id>:remove_yes
page:<n>
lang:en | lang:uk
flow:cancel
```

`msg:<id>:edit_date` is also used by **Edit date and interval**. The bot picks the flow from the message's recurrence.

## Telegram updates

| Update | Used for |
|---|---|
| `message` | Commands and typed input, private chats only |
| `callback_query` | Button presses |
| `my_chat_member` | Block and unblock: `kicked` means blocked, `member` means unblocked (confirm with a real bot, see [quickstart.md](../quickstart.md)) |

Updates from groups and channels are ignored, so nothing is stored for them (spec: private chats only).

## Telegram API calls

| Method | Used for |
|---|---|
| `getUpdates` | Long polling |
| `sendMessage` | Bot replies and scheduled messages |
| `editMessageText`, `answerCallbackQuery` | Button-driven screens |
| `setMyCommands` | Command menu, per language |
