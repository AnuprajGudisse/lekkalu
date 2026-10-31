# Copyright (c) 2026 Lekkalu
"""Database-level guarantees: constraints and the immutability trigger, bypassing the services."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.customers.models import Customer
from app.ledger.models import Transaction
from tests.conftest import make_business, make_customer, make_message

NOW = datetime(2026, 10, 31, 6, 0, tzinfo=UTC)


@pytest.fixture
def shop(session):
    return make_business(session)


@pytest.fixture
def sale(session, shop):
    msg = make_message(session, shop)
    tx = Transaction(business_id=shop.id, source_message_id=msg.id, type="sale", amount_paise=250000, occurred_at=NOW)
    session.add(tx)
    session.flush()
    return tx


def rejected(session, sql: str, match: str = "ledger rows are immutable", **params):
    with pytest.raises(DBAPIError, match=match), session.begin_nested():
        session.execute(text(sql), params)


def insert_rejected(session, match: str, **fields):
    with pytest.raises(DBAPIError, match=match), session.begin_nested():
        session.add(Transaction(occurred_at=NOW, **fields))
        session.flush()


def test_direct_update_rejected(session, sale):
    rejected(session, "UPDATE transactions SET amount_paise = 1 WHERE id = :id", id=sale.id)


def test_delete_rejected(session, sale):
    rejected(session, "DELETE FROM transactions WHERE id = :id", id=sale.id)


def test_truncate_rejected(session, sale):
    rejected(session, "TRUNCATE transactions CASCADE")


def test_void_link_can_be_set_once(session, shop, sale):
    void_msg = make_message(session, shop)
    session.execute(
        text("UPDATE transactions SET voided_at = now(), voided_by_message_id = :m WHERE id = :id"),
        {"m": void_msg.id, "id": sale.id},
    )
    other = make_message(session, shop)
    rejected(
        session,
        "UPDATE transactions SET voided_at = now(), voided_by_message_id = :m WHERE id = :id",
        m=other.id,
        id=sale.id,
    )


def test_voiding_while_changing_amount_rejected(session, shop, sale):
    void_msg = make_message(session, shop)
    rejected(
        session,
        "UPDATE transactions SET voided_at = now(), voided_by_message_id = :m, amount_paise = 1 WHERE id = :id",
        m=void_msg.id,
        id=sale.id,
    )


def test_replaced_by_without_void_rejected(session, sale):
    rejected(session, "UPDATE transactions SET replaced_by_id = id WHERE id = :id", id=sale.id)


def test_invalid_amounts_and_types_rejected(session, shop):
    msg = make_message(session, shop)
    base = dict(business_id=shop.id, source_message_id=msg.id)
    insert_rejected(session, "amount_positive", **base, type="sale", amount_paise=0)
    insert_rejected(session, "amount_positive", **base, type="sale", amount_paise=-1)
    insert_rejected(session, "quantity_positive", **base, type="sale", amount_paise=100, quantity=0)
    insert_rejected(session, "cost_non_negative", **base, type="sale", amount_paise=100, cost_paise=-1)
    insert_rejected(session, "cost_only_on_sales", **base, type="purchase", amount_paise=100, cost_paise=50)
    insert_rejected(session, "credit_has_customer", **base, type="credit_sale", amount_paise=100)
    insert_rejected(session, "credit_has_customer", **base, type="payment_received", amount_paise=100)
    insert_rejected(session, "ck_transactions_type", **base, type="gift", amount_paise=100)


def test_duplicate_source_line_rejected(session, shop, sale):
    insert_rejected(
        session,
        "uq_transactions_source_message_id_line_no",
        business_id=shop.id, source_message_id=sale.source_message_id, type="sale", amount_paise=100
    )


def test_replacement_sources_from_correction_message(session, shop, sale):
    correction = make_message(session, shop)
    replacement = Transaction(
        business_id=shop.id,
        source_message_id=correction.id,
        type="sale",
        amount_paise=200000,
        occurred_at=sale.occurred_at,
    )
    session.add(replacement)
    session.flush()
    session.execute(
        text(
            "UPDATE transactions SET voided_at = now(), voided_by_message_id = :m, replaced_by_id = :r "
            "WHERE id = :id"
        ),
        {"m": correction.id, "r": replacement.id, "id": sale.id},
    )
    original = session.execute(text("SELECT amount_paise, replaced_by_id FROM transactions WHERE id = :id"), {"id": sale.id}).one()
    assert original == (250000, replacement.id)


def test_new_customer_and_first_credit_sale_roll_back_together(session, shop):
    before = session.scalar(select(func.count()).select_from(Customer))
    nested = session.begin_nested()
    customer = make_customer(session, shop, "Padma")
    msg = make_message(session, shop)
    session.add(
        Transaction(
            business_id=shop.id,
            customer_id=customer.id,
            source_message_id=msg.id,
            type="credit_sale",
            amount_paise=250000,
            occurred_at=NOW,
        )
    )
    session.flush()
    nested.rollback()
    assert session.scalar(select(func.count()).select_from(Customer)) == before
    assert session.scalar(select(func.count()).select_from(Transaction).where(Transaction.business_id == shop.id)) == 0


def test_credit_sale_with_cost_accepted(session, shop):
    customer = make_customer(session, shop)
    msg = make_message(session, shop)
    session.add(
        Transaction(
            business_id=shop.id,
            customer_id=customer.id,
            source_message_id=msg.id,
            type="credit_sale",
            amount_paise=250000,
            cost_paise=200000,
            occurred_at=NOW,
        )
    )
    session.flush()


def test_replaced_by_requires_void_on_insert(session, shop, sale):
    msg = make_message(session, shop)
    insert_rejected(
        session,
        "replaced_implies_voided",
        business_id=shop.id,
        source_message_id=msg.id,
        type="sale",
        amount_paise=100,
        replaced_by_id=sale.id,
    )


def test_void_without_voiding_message_rejected(session, sale):
    # The trigger lets this UPDATE through; only the CHECK records who voided the row.
    rejected(session, "UPDATE transactions SET voided_at = now() WHERE id = :id", match="void_link_complete", id=sale.id)


def test_row_cannot_replace_itself(session, shop, sale):
    void_msg = make_message(session, shop)
    rejected(
        session,
        "UPDATE transactions SET voided_at = now(), voided_by_message_id = :m, replaced_by_id = id WHERE id = :id",
        match="not_replaced_by_self",
        m=void_msg.id,
        id=sale.id,
    )


def test_customer_from_another_business_rejected(session, shop):
    other_customer = make_customer(session, make_business(session))
    msg = make_message(session, shop)
    insert_rejected(
        session,
        "fk_transactions_business_id_customer_id_customers",
        business_id=shop.id,
        customer_id=other_customer.id,
        source_message_id=msg.id,
        type="credit_sale",
        amount_paise=100,
    )


def test_message_from_another_business_rejected(session, shop):
    other_msg = make_message(session, make_business(session))
    insert_rejected(
        session,
        "fk_transactions_business_id_source_message_id_messages",
        business_id=shop.id,
        source_message_id=other_msg.id,
        type="sale",
        amount_paise=100,
    )


def test_void_by_another_business_message_rejected(session, sale):
    other_msg = make_message(session, make_business(session))
    rejected(
        session,
        "UPDATE transactions SET voided_at = now(), voided_by_message_id = :m WHERE id = :id",
        match="fk_transactions_business_id_voided_by_message_id_messages",
        m=other_msg.id,
        id=sale.id,
    )


def test_replacement_from_another_business_rejected(session, shop, sale):
    other = make_business(session)
    other_msg = make_message(session, other)
    foreign = Transaction(business_id=other.id, source_message_id=other_msg.id, type="sale", amount_paise=100, occurred_at=NOW)
    session.add(foreign)
    session.flush()
    void_msg = make_message(session, shop)
    rejected(
        session,
        "UPDATE transactions SET voided_at = now(), voided_by_message_id = :m, replaced_by_id = :r WHERE id = :id",
        match="fk_transactions_business_id_replaced_by_id_transactions",
        m=void_msg.id,
        r=foreign.id,
        id=sale.id,
    )
