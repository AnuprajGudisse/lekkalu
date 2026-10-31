# Copyright (c) 2026 Lekkalu
"""Ledger results. All money is int paise."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ledger.models import Transaction


class RecordResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    transaction: Transaction
    created: bool


class VoidResult(BaseModel):
    status: Literal["voided", "already_done", "already_removed"]


class CustomerBalance(BaseModel):
    customer_id: int
    name: str
    name_native: str | None
    amount_paise: int  # always positive; the list it sits in says which way it runs


class BalancesSummary(BaseModel):
    owed: list[CustomerBalance]
    advances: list[CustomerBalance]
    total_receivable: int


class PeriodSummary(BaseModel):
    sales_revenue: int
    cash_received: int
    purchases: int
    expenses: int
    known_profit: int  # gross profit on sales with known cost; purchases and expenses not subtracted
    sales_with_known_cost: int
    sales_count: int


class NotCorrectable(Exception):
    """The entry was already voided by a different message."""
