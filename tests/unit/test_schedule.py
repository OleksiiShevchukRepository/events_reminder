import itertools
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from reminder_bot.domain.schedule import (
    Recurrence,
    Rule,
    first_send,
    kyiv_to_utc,
    next_after,
)

KYIV = ZoneInfo("Europe/Kyiv")


def kyiv(*args: int) -> datetime:
    return datetime(*args, tzinfo=KYIV).astimezone(UTC)


def rule(
    recurrence: Recurrence,
    start: date,
    send_time: time = time(14, 45),
    interval_days: int | None = None,
) -> Rule:
    return Rule(recurrence, start, send_time, interval_days)


def sequence(r: Rule, count: int) -> list[date]:
    """The first `count` send dates in Kyiv, walking forward with next_after."""
    moment = first_send(r) - timedelta(seconds=1)
    result = []
    for _ in range(count):
        moment = next_after(r, moment)
        result.append(moment.astimezone(KYIV).date())
    return result


def test_interval_every_10_days_crosses_months() -> None:
    r = rule(Recurrence.INTERVAL, date(2026, 11, 7), interval_days=10)
    assert sequence(r, 4) == [
        date(2026, 11, 7),
        date(2026, 11, 17),
        date(2026, 11, 27),
        date(2026, 12, 7),
    ]


def test_monthly_short_months() -> None:
    r = rule(Recurrence.MONTHLY, date(2027, 1, 29))
    assert sequence(r, 3) == [date(2027, 1, 29), date(2027, 2, 28), date(2027, 3, 29)]
    # 29 February exists in the leap year 2028.
    leap = next_after(r, kyiv(2028, 2, 1))
    assert leap.astimezone(KYIV).date() == date(2028, 2, 29)


def test_monthly_31st_returns_to_31st_after_shorter_months() -> None:
    r = rule(Recurrence.MONTHLY, date(2027, 1, 31))
    assert sequence(r, 5) == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
        date(2027, 4, 30),
        date(2027, 5, 31),
    ]


def test_yearly_29_february_uses_28_in_non_leap_years() -> None:
    r = rule(Recurrence.YEARLY, date(2028, 2, 29))
    assert sequence(r, 5) == [
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),
    ]


def test_yearly_same_date() -> None:
    r = rule(Recurrence.YEARLY, date(2027, 6, 5))
    assert sequence(r, 3) == [date(2027, 6, 5), date(2028, 6, 5), date(2029, 6, 5)]


def test_weekly_keeps_weekday_7_days_apart() -> None:
    r = rule(Recurrence.WEEKLY, date(2026, 11, 11))  # A Wednesday.
    dates = sequence(r, 60)
    assert {d.weekday() for d in dates} == {2}
    assert all((b - a).days == 7 for a, b in itertools.pairwise(dates))


def test_daily_sends_every_day() -> None:
    r = rule(Recurrence.DAILY, date(2026, 11, 7))
    dates = sequence(r, 40)
    assert all((b - a).days == 1 for a, b in itertools.pairwise(dates))


def test_once_has_no_send_after_its_date() -> None:
    r = rule(Recurrence.ONCE, date(2026, 11, 7))
    assert first_send(r) == kyiv(2026, 11, 7, 14, 45)
    assert next_after(r, kyiv(2026, 11, 7, 14, 44)) == kyiv(2026, 11, 7, 14, 45)
    assert next_after(r, kyiv(2026, 11, 7, 14, 45)) is None


def test_next_after_is_strictly_after_the_moment() -> None:
    r = rule(Recurrence.DAILY, date(2026, 11, 7))
    assert next_after(r, kyiv(2026, 11, 8, 14, 45)) == kyiv(2026, 11, 9, 14, 45)
    assert next_after(r, kyiv(2026, 11, 8, 14, 44)) == kyiv(2026, 11, 8, 14, 45)


def test_next_after_before_start_returns_the_start() -> None:
    r = rule(Recurrence.MONTHLY, date(2027, 5, 10))
    assert next_after(r, kyiv(2020, 1, 1)) == kyiv(2027, 5, 10, 14, 45)


def test_missed_sends_collapse_to_the_next_future_one() -> None:
    r = rule(Recurrence.INTERVAL, date(2026, 1, 1), interval_days=10)
    # Long after the start, the answer stays on the original 10-day grid.
    result = next_after(r, kyiv(2026, 6, 15, 12, 0)).astimezone(KYIV).date()
    assert (result - date(2026, 1, 1)).days % 10 == 0
    assert result > date(2026, 6, 15)
    assert (result - date(2026, 6, 15)).days <= 10


def test_skipped_kyiv_time_moves_to_next_valid_time() -> None:
    # Kyiv clocks jump from 03:00 to 04:00 on 28 March 2027.
    assert kyiv_to_utc(date(2027, 3, 28), time(3, 30)) == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)
    assert kyiv_to_utc(date(2027, 3, 28), time(3, 0)) == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)


def test_time_just_outside_the_gap_is_unchanged() -> None:
    assert kyiv_to_utc(date(2027, 3, 28), time(2, 59)) == datetime(2027, 3, 28, 0, 59, tzinfo=UTC)
    assert kyiv_to_utc(date(2027, 3, 28), time(4, 0)) == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)


def test_repeated_kyiv_time_uses_the_first_occurrence_only() -> None:
    # Kyiv clocks go back from 04:00 to 03:00 on 31 October 2027.
    first = kyiv_to_utc(date(2027, 10, 31), time(3, 30))
    assert first == datetime(2027, 10, 31, 0, 30, tzinfo=UTC)
    r = rule(Recurrence.DAILY, date(2027, 10, 30), time(3, 30))
    assert next_after(r, first).astimezone(KYIV).date() == date(2027, 11, 1)


def test_local_time_is_kept_across_clock_changes() -> None:
    r = rule(Recurrence.DAILY, date(2027, 3, 1), time(14, 45))
    moment = first_send(r) - timedelta(seconds=1)
    for _ in range(365):
        moment = next_after(r, moment)
        assert moment.astimezone(KYIV).time() == time(14, 45)


@pytest.mark.parametrize(
    ("recurrence", "interval"),
    [
        (Recurrence.DAILY, None),
        (Recurrence.WEEKLY, None),
        (Recurrence.MONTHLY, None),
        (Recurrence.YEARLY, None),
        (Recurrence.INTERVAL, 13),
    ],
)
def test_full_year_of_sends_strictly_increases_and_matches_direct_lookup(
    recurrence: Recurrence, interval: int | None
) -> None:
    r = rule(recurrence, date(2027, 1, 31), time(3, 30), interval)
    moment = first_send(r) - timedelta(seconds=1)
    end = moment + timedelta(days=366 * 2)
    sends = []
    while moment < end:
        following = next_after(r, moment)
        assert following > moment
        sends.append(following)
        moment = following
    # Asking from any moment between two sends gives the later one.
    for earlier, later in itertools.pairwise(sends):
        assert next_after(r, earlier + (later - earlier) / 2) == later


def test_rule_requires_a_valid_interval_only_for_interval_messages() -> None:
    with pytest.raises(ValueError):
        Rule(Recurrence.INTERVAL, date(2027, 1, 1), time(9, 0), None)
    with pytest.raises(ValueError):
        Rule(Recurrence.DAILY, date(2027, 1, 1), time(9, 0), 5)
