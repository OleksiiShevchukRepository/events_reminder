"""Pure parsing and validation of user input.

Errors are translation keys, so each caller can show them in the user's language.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from reminder_bot.domain.schedule import KYIV, kyiv_to_utc

MAX_TEXT_UTF16_UNITS = 4096
MAX_INTERVAL_DAYS = 3650
MAX_DATE = date(2100, 12, 31)

_DATE_PATTERN = re.compile(r"([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})")
_TIME_PATTERN = re.compile(r"([0-9]{1,2}):([0-9]{2})")
_INTERVAL_PATTERN = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class Parsed[T]:
    value: T | None = None
    error: str | None = None


def parse_date(text: str) -> Parsed[date]:
    match = _DATE_PATTERN.fullmatch(text.strip())
    if match is None:
        return Parsed(error="error_date_invalid")
    day, month, year = (int(part) for part in match.groups())
    try:
        parsed = date(year, month, day)
    except ValueError:
        return Parsed(error="error_date_invalid")
    if parsed > MAX_DATE:
        return Parsed(error="error_date_too_far")
    return Parsed(value=parsed)


def parse_time(text: str) -> Parsed[time]:
    match = _TIME_PATTERN.fullmatch(text.strip())
    if match is None:
        return Parsed(error="error_time_invalid")
    try:
        return Parsed(value=time(int(match.group(1)), int(match.group(2))))
    except ValueError:
        return Parsed(error="error_time_invalid")


def parse_interval(text: str) -> Parsed[int]:
    stripped = text.strip()
    if _INTERVAL_PATTERN.fullmatch(stripped) is None:
        return Parsed(error="error_interval_invalid")
    days = int(stripped)
    if not 1 <= days <= MAX_INTERVAL_DAYS:
        return Parsed(error="error_interval_invalid")
    return Parsed(value=days)


def parse_text(text: str | None) -> Parsed[str]:
    """Validate message text. It is stored exactly as entered."""
    if text is None or not text.strip():
        return Parsed(error="error_text_empty")
    if len(text.encode("utf-16-le")) // 2 > MAX_TEXT_UTF16_UNITS:
        return Parsed(error="error_text_too_long")
    return Parsed(value=text)


def today_in_kyiv(now: datetime) -> date:
    return now.astimezone(KYIV).date()


def date_not_past(day: date, now: datetime) -> str | None:
    """Return an error key if `day` is before today in Kyiv."""
    return "error_date_past" if day < today_in_kyiv(now) else None


def datetime_in_future(day: date, send_time: time, now: datetime) -> str | None:
    """Return an error key unless the date and time together are still ahead in Kyiv."""
    return None if kyiv_to_utc(day, send_time) > now else "error_datetime_past"
