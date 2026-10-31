# Copyright (c) 2026 Lekkalu
from datetime import UTC, date, datetime, timedelta

import pytest

from app.ledger import services as ledger
from app.ledger.models import Transaction
from app.ledger.rules import day_bounds
from app.ledger.schemas import NotCorrectable
from tests.conftest import make_business, make_customer, make_message

YESTERDAY = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)  # 11:30 IST, 30 Oct
TODAY = datetime(2026, 10, 31, 6, 0, tzinfo=UTC)


@pytest.fixture
def shop(session):
    return make_business(session)


@pytest.fixture
def lakshmi(session, shop):
    return make_customer(session, shop, "Lakshmi")


def rec(session, shop, *, at=TODAY, **kw):
    msg = make_message(session, shop, received_at=at)
    return ledger.record(session, business_id=shop.id, source_message_id=msg.id, occurred_at=at, **kw).transaction


def test_spec_acceptance_credit_repayment_and_correction(session, shop, lakshmi):
    sale = rec(session, shop, type="credit_sale", amount_paise=250000, customer_id=lakshmi.id)
    rec(session, shop, type="payment_received", amount_paise=100000, customer_id=lakshmi.id)
    assert ledger.customer_balance(session, customer_id=lakshmi.id) == 150000

    fix = make_message(session, shop)
    ledger.correct(session, original_id=sale.id, correction_message_id=fix.id, amount_paise=200000)
    assert ledger.customer_balance(session, customer_id=lakshmi.id) == 100000

    session.expire_all()
    original = session.get(Transaction, sale.id)
    assert original.amount_paise == 250000
    assert original.voided_by_message_id == fix.id
    assert original.replaced_by_id is not None


def test_correcting_yesterdays_sale_today_keeps_it_on_yesterday(session, shop):
    sale = rec(session, shop, at=YESTERDAY, type="sale", amount_paise=100000)
    rec(session, shop, type="sale", amount_paise=50000)
    fix = make_message(session, shop, received_at=TODAY)
    ledger.correct(session, original_id=sale.id, correction_message_id=fix.id, amount_paise=120000)

    def revenue(d):
        start, end = day_bounds(d)
        return ledger.period_summary(session, business_id=shop.id, start=start, end=end).sales_revenue

    assert revenue(date(2026, 10, 30)) == 120000
    assert revenue(date(2026, 10, 31)) == 50000


def test_correction_with_explicit_occurred_at_moves_it(session, shop):
    sale = rec(session, shop, at=YESTERDAY, type="sale", amount_paise=100000)
    fix = make_message(session, shop)
    r = ledger.correct(session, original_id=sale.id, correction_message_id=fix.id, occurred_at=TODAY)
    assert r.transaction.occurred_at == TODAY
    assert r.transaction.amount_paise == 100000


def test_correct_rejects_unknown_fields(session, shop):
    sale = rec(session, shop, type="sale", amount_paise=100000)
    with pytest.raises(ValueError):
        ledger.correct(session, original_id=sale.id, correction_message_id=make_message(session, shop).id, business_id=9)


def test_record_twice_with_same_source_is_one_row(session, shop):
    msg = make_message(session, shop)
    kw = dict(business_id=shop.id, source_message_id=msg.id, type="sale", amount_paise=100000, occurred_at=TODAY)
    first = ledger.record(session, **kw)
    second = ledger.record(session, **kw)
    assert (first.created, second.created) == (True, False)
    assert first.transaction.id == second.transaction.id


def test_correct_twice_with_same_message_is_one_replacement(session, shop):
    sale = rec(session, shop, type="sale", amount_paise=100000)
    fix = make_message(session, shop)
    first = ledger.correct(session, original_id=sale.id, correction_message_id=fix.id, amount_paise=90000)
    second = ledger.correct(session, original_id=sale.id, correction_message_id=fix.id, amount_paise=90000)
    assert (first.created, second.created) == (True, False)
    assert first.transaction.id == second.transaction.id
    with pytest.raises(NotCorrectable):
        ledger.correct(session, original_id=sale.id, correction_message_id=make_message(session, shop).id)


def test_void_is_idempotent_per_message(session, shop):
    sale = rec(session, shop, type="sale", amount_paise=100000)
    msg = make_message(session, shop)
    assert ledger.void(session, transaction_id=sale.id, message_id=msg.id).status == "voided"
    assert ledger.void(session, transaction_id=sale.id, message_id=msg.id).status == "already_done"
    other = make_message(session, shop)
    assert ledger.void(session, transaction_id=sale.id, message_id=other.id).status == "already_removed"


def test_voided_rows_are_excluded_from_every_total(session, shop, lakshmi):
    credit = rec(session, shop, type="credit_sale", amount_paise=250000, customer_id=lakshmi.id, cost_paise=200000)
    ledger.void(session, transaction_id=credit.id, message_id=make_message(session, shop).id)
    assert ledger.customer_balance(session, customer_id=lakshmi.id) == 0
    assert ledger.balances(session, business_id=shop.id).owed == []
    s = ledger.period_summary(session, business_id=shop.id, start=TODAY - timedelta(days=1), end=TODAY + timedelta(days=1))
    assert (s.sales_revenue, s.known_profit, s.sales_count) == (0, 0, 0)
    assert ledger.latest_entry(session, business_id=shop.id, now=datetime.now(UTC)) is None


def test_overpayment_becomes_an_advance(session, shop, lakshmi):
    padma = make_customer(session, shop, "Padma")
    rec(session, shop, type="credit_sale", amount_paise=150000, customer_id=lakshmi.id)
    rec(session, shop, type="payment_received", amount_paise=200000, customer_id=lakshmi.id)
    rec(session, shop, type="credit_sale", amount_paise=30000, customer_id=padma.id)
    assert ledger.customer_balance(session, customer_id=lakshmi.id) == -50000

    b = ledger.balances(session, business_id=shop.id)
    assert [(x.name, x.amount_paise) for x in b.advances] == [("Lakshmi", 50000)]
    assert [(x.name, x.amount_paise) for x in b.owed] == [("Padma", 30000)]
    assert b.total_receivable == 30000


def test_known_profit_counts_only_sales_with_known_cost(session, shop, lakshmi):
    rec(session, shop, type="sale", amount_paise=100000, cost_paise=80000)
    rec(session, shop, type="sale", amount_paise=50000)
    rec(session, shop, type="credit_sale", amount_paise=250000, customer_id=lakshmi.id)
    rec(session, shop, type="payment_received", amount_paise=40000, customer_id=lakshmi.id)
    rec(session, shop, type="purchase", amount_paise=1500000)
    rec(session, shop, type="expense", amount_paise=15000)

    s = ledger.period_summary(session, business_id=shop.id, start=TODAY - timedelta(hours=1), end=TODAY + timedelta(hours=1))
    assert s.model_dump() == {
        "sales_revenue": 400000,
        "cash_received": 190000,
        "purchases": 1500000,
        "expenses": 15000,
        "known_profit": 20000,
        "sales_with_known_cost": 1,
        "sales_count": 3,
    }


def test_latest_entry_skips_voided_and_older_than_a_day(session, shop):
    now = datetime.now(UTC)
    old_msg = make_message(session, shop)
    old = Transaction(business_id=shop.id, source_message_id=old_msg.id, type="sale", amount_paise=100,
                      occurred_at=now, created_at=now - timedelta(hours=25))
    session.add(old)
    session.flush()
    assert ledger.latest_entry(session, business_id=shop.id, now=now) is None

    keep = rec(session, shop, type="sale", amount_paise=200)
    gone = rec(session, shop, type="sale", amount_paise=300)
    ledger.void(session, transaction_id=gone.id, message_id=make_message(session, shop).id)
    assert ledger.latest_entry(session, business_id=shop.id, now=now).id == keep.id
