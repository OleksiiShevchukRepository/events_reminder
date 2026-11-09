"""English bot text. uk.py must have identical keys and placeholders."""

TEXT = {
    "welcome": (
        "Hi! I send you reminders at the time you choose.\n\n"
        "You can create a reminder once or on a repeating schedule, see all your reminders, "
        "and change or remove them.\n\n"
        "All times are Kyiv time."
    ),
    "help": (
        "Here's what I can do:\n\n"
        "/new - create a reminder\n"
        "/list - see, change or remove your reminders\n"
        "/language - change the language\n"
        "/cancel - stop what you're doing\n"
        "/help - show this help\n\n"
        "All times are Kyiv time."
    ),
    "menu_prompt": "What would you like to do?",
    "unknown_input": "I didn't understand that. Choose an action below or send /help.",
    "cancelled": "Cancelled. Nothing was changed.",
    "nothing_to_cancel": "There's nothing to cancel.",
    "no_longer_available": "This is no longer available.",
    # Buttons
    "btn_new": "New reminder",
    "btn_list": "My reminders",
    "btn_language": "Language",
    "btn_cancel": "Cancel",
    "btn_back": "Back",
    "btn_previous": "Previous",
    "btn_next": "Next",
    "btn_edit_text": "Edit text",
    "btn_edit_recurrence": "Edit recurrence",
    "btn_edit_date": "Edit date",
    "btn_edit_date_interval": "Edit date and interval",
    "btn_edit_time": "Edit time",
    "btn_remove": "Remove",
    "btn_remove_yes": "Yes, remove",
    "btn_keep": "Keep",
    # Recurrence
    "rec_once": "Only once",
    "rec_daily": "Every day",
    "rec_weekly": "Every week",
    "rec_monthly": "Every month",
    "rec_yearly": "Every year",
    "rec_interval": "Every N days",
    "rec_every_n_days": "Every {days} days",
    # Prompts
    "prompt_text": "Send the text of your reminder.",
    "prompt_recurrence": "How often should it be sent?",
    "prompt_interval": "How many days between reminders? Send a whole number from 1 to 3650.",
    "prompt_date": "On what date should the first reminder be sent? For example: 7.11.2026",
    "prompt_date_once": "On what date should it be sent? For example: 7.11.2026",
    "prompt_time": "At what time? For example: 14:45 (Kyiv time)",
    "prompt_new_text": "Send the new text.",
    "prompt_new_recurrence": "Choose the new recurrence.",
    "prompt_new_date": "Send the new date. For example: 7.11.2026",
    "prompt_new_interval": "Send the new number of days between reminders, from 1 to 3650.",
    "prompt_new_time": "Send the new time. For example: 14:45 (Kyiv time)",
    # Errors
    "error_text_empty": "Please send the reminder as text. It can't be empty.",
    "error_text_too_long": "That text is too long. The limit is 4,096 characters.",
    "error_date_invalid": "That isn't a valid date. Use day.month.year, for example 7.11.2026.",
    "error_date_too_far": "That date is too far ahead. The latest date is 31.12.2100.",
    "error_date_past": "That date has passed. Send today's date or a later one.",
    "error_datetime_past": "That time has passed. Send a time in the future (Kyiv time).",
    "error_time_invalid": "That isn't a valid time. Use 24-hour time, for example 14:45.",
    "error_interval_invalid": "Send a whole number from 1 to 3650.",
    "error_choose_button": "Please choose one of the buttons above.",
    "error_limit": (
        "You've reached the limit of 100 active reminders. Remove one to create another."
    ),
    # Confirmations
    "saved": "Saved.\n\n{summary}",
    "updated": "Updated.\n\n{summary}",
    "removed": "Removed.",
    "remove_confirm": "Remove this reminder? This can't be undone.\n\n{text}",
    "summary": "{text}\n\n{recurrence}, {time} (Kyiv time)\nNext send: {next_send}",
    # List
    "list_empty": "You don't have any reminders yet.",
    "list_title": "Your reminders (page {page} of {pages}):",
    "list_entry": "{number}. {preview}\n{recurrence}, {time} | Next: {next_send} | {status}",
    "screen": (
        "{text}\n\n"
        "Recurrence: {recurrence}\n"
        "Time: {time} (Kyiv time)\n"
        "Next send: {next_send}\n"
        "Status: {status}"
    ),
    "status_active": "Active",
    "status_completed": "Completed",
    "status_not_delivered": "Not delivered",
    "next_sending": "Sending",
    "next_none": "None",
    # Delivery
    "overdue_note": "This reminder was due on {when} (Kyiv time):",
    # Language
    "language_prompt": "Choose your language.",
    "language_changed": "Language changed to English.",
    # Groups (specs/002-group-reminders)
    "welcome_group": (
        "Hi! I post reminders in this group at the time you choose.\n\n"
        "Send /new to create one and /list to see, change or remove them. Any member can "
        "manage the group's reminders. They're posted here for everyone, in the General "
        "topic if the group has topics.\n\n"
        "Answer my questions by replying to them. Making me an admin allowed to delete "
        "messages keeps the chat tidy and lets you answer without replying.\n\n"
        "All times are Kyiv time."
    ),
    "help_group": (
        "Here's what I can do in this group:\n\n"
        "/new - create a reminder for the group\n"
        "/list - see, change or remove the group's reminders\n"
        "/language - change the language for the group\n"
        "/cancel - stop what you're doing\n"
        "/help - show this help\n\n"
        "Answer my questions by replying to them. All times are Kyiv time."
    ),
    "cancel_hint": "Reply to this message. Send /cancel to stop.",
    "not_your_request": "This isn't your request.",
    "anonymous_admin": (
        "Anonymous admins can't create, change or remove reminders. Turn off "
        '"Remain anonymous" in your admin rights first. /list still works.'
    ),
    "saved_by": "Saved by {name}.\n\n{summary}",
    "updated_by": "Updated by {name}.\n\n{summary}",
    "removed_by": "Removed by {name}:\n\n{text}",
    "created_by": "Created by: {name}",
    "changed_by": "Last changed by: {name}",
    # Bot command menu
    "command_new": "Create a reminder",
    "command_list": "See your reminders",
    "command_language": "Change the language",
    "command_help": "Show what the bot can do",
    "command_cancel": "Stop what you're doing",
}
