# Copyright (c) 2026 Lekkalu
"""Ledger operations. Callers own the transaction: these flush, never commit.

Every write is idempotent, keyed by the message that started it.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.customers.models import Customer
from app.ledger.models import Transaction
from app.ledger.rules import aware
from app.ledger.schemas import (
    BalancesSummary,
    CustomerBalance,
    NotCorrectable,
    PeriodSummary,
    RecordResult,
    VoidResult,
)

COPIED_ON_CORRECTION = (
    "business_id", "customer_id", "type", "amount_paise", "cost_paise", "item", "item_native", "quantity", "occurred_at",
)
# occurred_at is copied by default (a correction keeps the original business date) but may be
# changed on purpose: day2-task "correction with an explicit new occurred_at moves it".
CHANGEABLE = set(COPIED_ON_CORRECTION) - {"business_id"}
ACTIVE = Transaction.voided_at.is_(None)


def _by_source(session: Session, source_message_id: int, line_no: int) -> Transaction | None:
    return session.scalars(
        select(Transaction).where(Transaction.source_message_id == source_message_id, Transaction.line_no == line_no)
    ).one_or_none()


def record(
    session: Session,
    *,
    business_id: int,
    source_message_id: int,
    type: str,
    amount_paise: int,
    occurred_at: datetime,
    line_no: int = 1,
    customer_id: int | None = None,
    cost_paise: int | None = None,
    item: str | None = None,
    item_native: str | None = None,
    quantity: int | None = None,
) -> RecordResult:
    aware(occurred_at)
    if existing := _by_source(session, source_message_id, line_no):
        return RecordResult(transaction=existing, created=False)
    tx = Transaction(
        business_id=business_id, source_message_id=source_message_id, line_no=line_no, type=type,
        amount_paise=amount_paise, occurred_at=occurred_at, customer_id=customer_id, cost_paise=cost_paise,
        item=item, item_native=item_native, quantity=quantity,
    )
    try:
        with session.begin_nested():
            session.add(tx)
    except IntegrityError:
        # A concurrent insert for the same source message won; that row is the result.
        if existing := _by_source(session, source_message_id, line_no):
            return RecordResult(transaction=existing, created=False)
        raise
    return RecordResult(transaction=tx, created=True)


def correct(
    session: Session,
    *,
    original_id: int,
    correction_message_id: int,
    reason: str | None = None,
    **changed_fields,
) -> RecordResult:
    if bad := set(changed_fields) - CHANGEABLE:
        raise ValueError(f"cannot change {sorted(bad)}")
    original = session.get(Transaction, original_id, with_for_update=True)
    if original.voided_at is not None:
        if original.voided_by_message_id == correction_message_id and original.replaced_by_id is not None:
            return RecordResult(transaction=session.get(Transaction, original.replaced_by_id), created=False)
        raise NotCorrectable(original_id)

    fields = {f: getattr(original, f) for f in COPIED_ON_CORRECTION} | changed_fields
    result = record(session, source_message_id=correction_message_id, **fields)
    original.voided_at = datetime.now(UTC)
    original.voided_by_message_id = correction_message_id
    original.replaced_by_id = result.transaction.id
    original.correction_reason = reason
    session.flush()  # one UPDATE sets the whole void link, as the trigger requires
    return result


def void(session: Session, *, transaction_id: int, message_id: int, reason: str | None = None) -> VoidResult:
    tx = session.get(Transaction, transaction_id, with_for_update=True)
    if tx.voided_at is not None:
        return VoidResult(status="already_done" if tx.voided_by_message_id == message_id else "already_removed")
    tx.voided_at = datetime.now(UTC)
    tx.voided_by_message_id = message_id
    tx.correction_reason = reason
    session.flush()
    return VoidResult(status="voided")


def latest_entry(session: Session, *, business_id: int, now: datetime) -> Transaction | None:
    """Target of "తప్పు"/"తీసేయి". Only the last day, so an old entry is never changed by surprise."""
    return session.scalars(
        select(Transaction)
        .where(Transaction.business_id == business_id, ACTIVE, Transaction.created_at >= aware(now) - timedelta(hours=24))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(1)
    ).first()


def _sum(condition) -> object:
    return func.coalesce(func.sum(case((condition, Transaction.amount_paise), else_=0)), 0)


BALANCE = _sum(Transaction.type == "credit_sale") - _sum(Transaction.type == "payment_received")


def customer_balance(session: Session, *, customer_id: int) -> int:
    return int(session.scalar(select(BALANCE).where(Transaction.customer_id == customer_id, ACTIVE)))


def balances(session: Session, *, business_id: int) -> BalancesSummary:
    rows = session.execute(
        select(Customer.id, Customer.name, Customer.name_native, BALANCE.label("balance"))
        .join(Transaction, Transaction.customer_id == Customer.id)
        .where(Transaction.business_id == business_id, ACTIVE)
        .group_by(Customer.id)
        .order_by(Customer.name)
    ).all()
    entry = lambda r, amount: CustomerBalance(  # noqa: E731
        customer_id=r.id, name=r.name, name_native=r.name_native, amount_paise=amount
    )
    owed = [entry(r, int(r.balance)) for r in rows if r.balance > 0]
    advances = [entry(r, -int(r.balance)) for r in rows if r.balance < 0]
    return BalancesSummary(owed=owed, advances=advances, total_receivable=sum(b.amount_paise for b in owed))


def period_summary(session: Session, *, business_id: int, start: datetime, end: datetime) -> PeriodSummary:
    is_sale = Transaction.type.in_(("sale", "credit_sale"))
    known = is_sale & Transaction.cost_paise.is_not(None)
    row = session.execute(
        select(
            _sum(is_sale),
            _sum(Transaction.type.in_(("sale", "payment_received"))),
            _sum(Transaction.type == "purchase"),
            _sum(Transaction.type == "expense"),
            func.coalesce(func.sum(case((known, Transaction.amount_paise - Transaction.cost_paise), else_=0)), 0),
            func.count().filter(known),
            func.count().filter(is_sale),
        ).where(
            Transaction.business_id == business_id, ACTIVE,
            Transaction.occurred_at >= aware(start), Transaction.occurred_at < aware(end),
        )
    ).one()
    return PeriodSummary(**dict(zip(PeriodSummary.model_fields, map(int, row))))
