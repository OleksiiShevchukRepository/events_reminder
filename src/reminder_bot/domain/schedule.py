"""Pure send-date calculation.

Every send is calculated from a message's original start date, never from the
previous send. That is what lets a monthly message on the 31st return to the
31st after a shorter month instead of drifting to the 28th for good.
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")


class Recurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    INTERVAL = "interval"


@dataclass(frozen=True)
class Rule:
    recurrence: Recurrence
    start_date: date
    send_time: time
    interval_days: int | None = None

    def __post_init__(self) -> None:
        if (self.recurrence is Recurrence.INTERVAL) != (self.interval_days is not None):
            raise ValueError("interval_days is required for interval messages, and only for them")


def kyiv_to_utc(day: date, send_time: time) -> datetime:
    """Convert a Kyiv date and time to UTC.

    A time skipped by the spring clock change becomes the first valid moment
    after the gap. A time repeated by the autumn change uses its first occurrence.
    """
    wall = datetime.combine(day, send_time)
    # With fold=0, Python uses the offset from before a transition.
    before = wall.replace(tzinfo=KYIV, fold=0).astimezone(UTC)
    if before.astimezone(KYIV).replace(tzinfo=None) == wall:
        return before
    # The time doesn't exist. fold=1 gives the moment on the other side of the gap,
    # so the clock change lies between the two.
    low = wall.replace(tzinfo=KYIV, fold=1).astimezone(UTC)
    high = before
    offset = low.astimezone(KYIV).utcoffset()
    while high - low > timedelta(seconds=1):
        middle = low + (high - low) / 2
        if middle.astimezone(KYIV).utcoffset() == offset:
            low = middle
        else:
            high = middle
    return high.replace(microsecond=0)


def _add_months(start: date, months: int) -> date:
    month_index = start.year * 12 + (start.month - 1) + months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _nth_date(rule: Rule, n: int) -> date:
    match rule.recurrence:
        case Recurrence.ONCE:
            return rule.start_date
        case Recurrence.DAILY:
            return rule.start_date + timedelta(days=n)
        case Recurrence.WEEKLY:
            return rule.start_date + timedelta(days=7 * n)
        case Recurrence.INTERVAL:
            return rule.start_date + timedelta(days=(rule.interval_days or 1) * n)
        case Recurrence.MONTHLY:
            return _add_months(rule.start_date, n)
        case Recurrence.YEARLY:
            return _add_months(rule.start_date, 12 * n)


def _index_just_before(rule: Rule, day: date) -> int:
    """A send index that is certainly no later than the first send after `day`."""
    start = rule.start_date
    match rule.recurrence:
        case Recurrence.ONCE:
            return 0
        case Recurrence.DAILY:
            step = 1
        case Recurrence.WEEKLY:
            step = 7
        case Recurrence.INTERVAL:
            step = rule.interval_days or 1
        case Recurrence.MONTHLY:
            return max(0, (day.year - start.year) * 12 + day.month - start.month - 1)
        case Recurrence.YEARLY:
            return max(0, day.year - start.year - 1)
    return max(0, (day - start).days // step - 1)


def first_send(rule: Rule) -> datetime:
    """The message's first send, in UTC."""
    return kyiv_to_utc(rule.start_date, rule.send_time)


def next_after(rule: Rule, moment: datetime) -> datetime | None:
    """The first send strictly after `moment`, in UTC. None if there are no more."""
    if rule.recurrence is Recurrence.ONCE:
        send = first_send(rule)
        return send if send > moment else None

    n = _index_just_before(rule, moment.astimezone(KYIV).date())
    while True:
        send = kyiv_to_utc(_nth_date(rule, n), rule.send_time)
        if send > moment:
            return send
        n += 1
