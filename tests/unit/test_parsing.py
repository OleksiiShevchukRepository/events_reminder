from datetime import UTC, date, datetime, time

import pytest

from reminder_bot.domain.parsing import (
    date_not_past,
    datetime_in_future,
    parse_date,
    parse_interval,
    parse_text,
    parse_time,
    today_in_kyiv,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7.11.2026", date(2026, 11, 7)),
        ("07.11.2026", date(2026, 11, 7)),
        (" 7.11.2026 ", date(2026, 11, 7)),
        ("29.02.2028", date(2028, 2, 29)),
        ("31.12.2100", date(2100, 12, 31)),
    ],
)
def test_valid_dates(text: str, expected: date) -> None:
    result = parse_date(text)
    assert result.error is None
    assert result.value == expected


@pytest.mark.parametrize(
    "text",
    [
        "31.02.2027",
        "29.02.2027",
        "2026-11-07",
        "7/11/2026",
        "7.11",
        "abc",
        "",
        chr(0x667) + ".11.2026",  # An Arabic-Indic digit isn't accepted as a date.
    ],
)
def test_invalid_dates(text: str) -> None:
    assert parse_date(text).error == "error_date_invalid"


def test_date_after_2100_is_rejected() -> None:
    assert parse_date("1.1.2101").error == "error_date_too_far"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("14:45", time(14, 45)), ("9:05", time(9, 5)), ("00:00", time(0, 0)), ("23:59", time(23, 59))],
)
def test_valid_times(text: str, expected: time) -> None:
    result = parse_time(text)
    assert result.error is None
    assert result.value == expected


@pytest.mark.parametrize("text", ["25:70", "24:00", "14:5", "14.45", "1445", "abc", ""])
def test_invalid_times(text: str) -> None:
    assert parse_time(text).error == "error_time_invalid"


@pytest.mark.parametrize(("text", "expected"), [("1", 1), ("10", 10), ("3650", 3650)])
def test_valid_intervals(text: str, expected: int) -> None:
    result = parse_interval(text)
    assert result.error is None
    assert result.value == expected


@pytest.mark.parametrize("text", ["0", "3651", "1.5", "-3", "abc", ""])
def test_invalid_intervals(text: str) -> None:
    assert parse_interval(text).error == "error_interval_invalid"


def test_text_is_kept_as_entered() -> None:
    assert parse_text("  Pay rent  ").value == "  Pay rent  "


@pytest.mark.parametrize("text", [None, "", "   ", "\n\t"])
def test_blank_or_missing_text_is_rejected(text: str | None) -> None:
    assert parse_text(text).error == "error_text_empty"


def test_text_length_limit_is_exact() -> None:
    assert parse_text("a" * 4096).error is None
    assert parse_text("a" * 4097).error == "error_text_too_long"


def test_emoji_count_as_two_utf16_units() -> None:
    assert parse_text("😀" * 2048).error is None
    assert parse_text("😀" * 2048 + "a").error == "error_text_too_long"


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)  # 14:00 in Kyiv.


def test_today_uses_kyiv_date_not_utc_date() -> None:
    # 22:30 UTC on 6 November is already 7 November in Kyiv.
    assert today_in_kyiv(datetime(2026, 11, 6, 22, 30, tzinfo=UTC)) == date(2026, 11, 7)


def test_date_not_past() -> None:
    assert date_not_past(date(2026, 11, 6), NOW) is None
    assert date_not_past(date(2026, 11, 7), NOW) is None
    assert date_not_past(date(2026, 11, 5), NOW) == "error_date_past"


def test_datetime_in_future_uses_kyiv_time() -> None:
    assert datetime_in_future(date(2026, 11, 6), time(14, 1), NOW) is None
    assert datetime_in_future(date(2026, 11, 6), time(14, 0), NOW) == "error_datetime_past"
    assert datetime_in_future(date(2026, 11, 6), time(13, 59), NOW) == "error_datetime_past"
    assert datetime_in_future(date(2026, 11, 7), time(0, 0), NOW) is None
