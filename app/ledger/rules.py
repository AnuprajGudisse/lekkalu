# Copyright (c) 2026 Lekkalu
"""Pure ledger rules: business dates in IST and money arithmetic. No database."""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

TZ = ZoneInfo(get_settings().business_tz)


def aware(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"naive datetime not allowed: {ts!r}")
    return ts


def business_date(ts: datetime) -> date:
    return aware(ts).astimezone(TZ).date()


def _start(d: date) -> datetime:
    return datetime.combine(d, time(), TZ).astimezone(UTC)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    return _start(d), _start(d + timedelta(days=1))


def week_bounds(d: date) -> tuple[datetime, datetime]:
    monday = d - timedelta(days=d.weekday())
    return _start(monday), _start(monday + timedelta(days=7))


def derive_cost(amount_paise: int, profit_paise: int) -> int:
    if amount_paise < 0 or profit_paise < 0:
        raise ValueError("amount and profit must be non-negative")
    if profit_paise > amount_paise:
        raise ValueError("profit exceeds amount")
    return amount_paise - profit_paise


def repayment_needs_confirmation(amount_paise: int, outstanding_paise: int) -> bool:
    return amount_paise > outstanding_paise
