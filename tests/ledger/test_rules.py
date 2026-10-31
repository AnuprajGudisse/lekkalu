# Copyright (c) 2026 Lekkalu
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.ledger.rules import (
    business_date,
    day_bounds,
    derive_cost,
    repayment_needs_confirmation,
    week_bounds,
)

IST = timezone(timedelta(hours=5, minutes=30))


def test_late_sunday_and_early_monday_land_on_their_own_ist_dates():
    assert business_date(datetime(2026, 11, 1, 23, 59, tzinfo=IST)) == date(2026, 11, 1)
    assert business_date(datetime(2026, 11, 2, 0, 1, tzinfo=IST)) == date(2026, 11, 2)


def test_20_utc_is_the_next_ist_day():
    assert business_date(datetime(2026, 10, 31, 20, 0, tzinfo=UTC)) == date(2026, 11, 1)


def test_day_bounds_are_ist_midnights_in_utc():
    assert day_bounds(date(2026, 11, 1)) == (
        datetime(2026, 10, 31, 18, 30, tzinfo=UTC),
        datetime(2026, 11, 1, 18, 30, tzinfo=UTC),
    )


def test_every_day_of_a_week_shares_bounds_starting_monday_ist():
    expected = (datetime(2026, 11, 1, 18, 30, tzinfo=UTC), datetime(2026, 11, 8, 18, 30, tzinfo=UTC))
    for offset in range(7):  # Monday 2 Nov .. Sunday 8 Nov 2026
        assert week_bounds(date(2026, 11, 2) + timedelta(days=offset)) == expected


def test_derive_cost_from_profit():
    assert derive_cost(100000, 20000) == 80000
    with pytest.raises(ValueError):
        derive_cost(100000, 100001)
    with pytest.raises(ValueError):
        derive_cost(100000, -1)


def test_repayment_needs_confirmation_only_above_outstanding():
    assert repayment_needs_confirmation(1500000, 150000)
    assert not repayment_needs_confirmation(150000, 150000)
    assert repayment_needs_confirmation(100, 0)
    assert repayment_needs_confirmation(100, -50000)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="naive"):
        business_date(datetime(2026, 11, 1, 12, 0))
