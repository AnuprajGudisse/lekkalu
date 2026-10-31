# Copyright (c) 2026 Lekkalu
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ai.providers.mock import MockExtractor
from app.ai.schemas import Extraction, Line
from app.customers import services as customers
from app.ledger import services as ledger
from app.ledger.models import Transaction
from app.messaging import templates_te as t
from app.messaging.models import Message
from app.processing import pipeline
from tests.conftest import make_business, make_message

CREDIT_TEXT = "లక్ష్మి రెండు చీరలు తీసుకుంది, రెండు వేల ఐదు వందలు, తర్వాత ఇస్తుంది"


def line(intent="credit_sale", amount=None, name="Lakshmi", native="లక్ష్మి", **kw) -> Line:
    fields = dict(intent=intent, amount_rupees=None if amount is None else Decimal(amount), profit_rupees=None,
                  quantity=None, item=None, item_native=None, customer_name=name, customer_name_native=native,
                  missing_fields=[])
    return Line(**(fields | kw))


@pytest.fixture
def shop(session, db):
    return make_business(session)


@pytest.fixture
def lakshmi(session, shop):
    return customers.create(session, business_id=shop.id, name="Lakshmi", name_native="లక్ష్మి")


@pytest.fixture
def extract(monkeypatch):
    """Map message text -> extracted lines for the pipeline."""
    responses = {}
    monkeypatch.setattr(pipeline, "get_extractor", lambda: MockExtractor(responses))

    def add(text, *lines):
        responses[text] = Extraction(lines=list(lines))
    return add


def send(session, shop, text, **kw):
    return make_message(session, shop, body=text, **kw)


def transactions(session, shop):
    return session.scalars(select(Transaction).where(Transaction.business_id == shop.id).order_by(Transaction.id)).all()


def refreshed(session, msg):
    session.expire_all()
    return session.get(Message, msg.id)


def test_credit_sale_records_transaction_and_telugu_reply(session, shop, lakshmi, extract):
    extract(CREDIT_TEXT, line(amount="2500", quantity=2, item="saree", item_native="చీరలు"))
    msg = send(session, shop, CREDIT_TEXT)
    pipeline.process_business(shop.id)

    [tx] = transactions(session, shop)
    assert (tx.type, tx.amount_paise, tx.customer_id, tx.quantity) == ("credit_sale", 250000, lakshmi.id, 2)
    assert tx.occurred_at == msg.received_at
    msg = refreshed(session, msg)
    assert msg.status == "done"
    assert msg.reply_text.startswith("[MOCK] ")
    assert "₹2,500" in msg.reply_text and "లక్ష్మి" in msg.reply_text
    assert msg.extraction["lines"][0]["intent"] == "credit_sale"


def test_restart_mid_processing_yields_one_transaction_and_one_reply(session, shop, lakshmi, extract):
    extract(CREDIT_TEXT, line(amount="2500"))
    msg = send(session, shop, CREDIT_TEXT, status="processing")  # claimed, then the process died
    assert pipeline.recover() == [shop.id]
    pipeline.process_business(shop.id)
    pipeline.process_business(shop.id)

    assert len(transactions(session, shop)) == 1
    assert refreshed(session, msg).status == "done"


def test_reprocessing_a_done_message_changes_nothing(session, shop, lakshmi, extract):
    extract(CREDIT_TEXT, line(amount="2500"))
    msg = send(session, shop, CREDIT_TEXT)
    pipeline.process_business(shop.id)
    first_reply = refreshed(session, msg).reply_text
    pipeline.process_message(msg.id)  # even a direct re-run is idempotent

    assert len(transactions(session, shop)) == 1
    assert ledger.customer_balance(session, customer_id=lakshmi.id) == 250000
    assert refreshed(session, msg).reply_text == first_reply


def test_messages_processed_in_received_order(session, shop, lakshmi, extract):
    extract("credit", line(amount="2500"))
    extract("repay", line(intent="payment_received", amount="1000"))
    now = datetime.now(UTC)
    repay = send(session, shop, "repay", received_at=now + timedelta(milliseconds=100))
    credit = send(session, shop, "credit", received_at=now)  # inserted later, received earlier
    pipeline.process_business(shop.id)

    assert [tx.source_message_id for tx in transactions(session, shop)] == [credit.id, repay.id]
    assert ledger.customer_balance(session, customer_id=lakshmi.id) == 150000
    assert "₹1,500" in refreshed(session, repay).reply_text


def test_message_committed_while_lock_held_is_still_processed(session, shop, lakshmi, extract):
    extract(CREDIT_TEXT, line(amount="2500"))
    lock = pipeline._locks.setdefault(shop.id, threading.Lock())
    lock.acquire()
    send(session, shop, CREDIT_TEXT)
    pipeline.process_business(shop.id)  # lock taken: returns at once
    assert transactions(session, shop) == []
    lock.release()
    pipeline.process_business(shop.id)
    assert len(transactions(session, shop)) == 1


@pytest.mark.parametrize(
    ("lines", "reply"),
    [
        ([line(amount=None, missing_fields=["amount_rupees"])], t.ASK_AMOUNT),
        ([line(amount="2500", name="Ravi", native="రవి")], t.UNKNOWN_CUSTOMER),
        ([line(amount="2500", name=None, native=None)], t.UNKNOWN_CUSTOMER),
        ([line(intent="sale", amount="2000", name=None, native=None), line(intent="expense", amount="150")],
         t.SEND_SEPARATELY),
        ([line(intent="query", name=None, native=None)], t.NOT_YET),
        ([line(intent="other", name=None, native=None)], t.NOT_UNDERSTOOD),
        ([], t.NOT_UNDERSTOOD),
    ],
    ids=["missing_amount", "unknown_customer", "no_customer", "two_lines", "query", "other", "no_lines"],
)
def test_incomplete_or_unsupported_messages_reply_and_record_nothing(session, shop, lakshmi, extract, lines, reply):
    extract("msg", *lines)
    msg = send(session, shop, "msg")
    pipeline.process_business(shop.id)

    assert transactions(session, shop) == []
    msg = refreshed(session, msg)
    assert (msg.status, msg.reply_text) == ("done", f"[MOCK] {reply}")


def test_sale_with_profit_records_derived_cost(session, shop, extract):
    extract("sale", line(intent="sale", amount="1000", profit_rupees=Decimal("200"), name=None, native=None))
    send(session, shop, "sale")
    pipeline.process_business(shop.id)
    [tx] = transactions(session, shop)
    assert (tx.amount_paise, tx.cost_paise, tx.customer_id) == (100000, 80000, None)


@pytest.mark.parametrize(
    "bad",
    [
        line(amount="2500", missing_fields=["amount_rupees"]),
        line(amount="0"),
        line(amount="-500"),
        line(amount="2500.001"),
        line(intent="sale", amount="100", profit_rupees=Decimal("200"), name=None, native=None),
    ],
    ids=["listed_missing", "zero", "negative", "fractional_paise", "profit_above_amount"],
)
def test_unusable_amounts_ask_again_and_record_nothing(session, shop, lakshmi, extract, bad):
    extract("bad", bad)
    msg = send(session, shop, "bad")
    pipeline.process_business(shop.id)
    assert transactions(session, shop) == []
    msg = refreshed(session, msg)
    assert (msg.status, msg.reply_text) == ("done", f"[MOCK] {t.ASK_AMOUNT}")


def test_zero_profit_means_cost_equals_amount(session, shop, extract):
    extract("sale", line(intent="sale", amount="1000", profit_rupees=Decimal("0"), name=None, native=None))
    send(session, shop, "sale")
    pipeline.process_business(shop.id)
    [tx] = transactions(session, shop)
    assert tx.cost_paise == 100000


def test_fuzzy_name_is_not_recorded_against_the_close_customer(session, shop, lakshmi, extract):
    extract("laxmi", line(amount="2500", name="Laxmi", native=None))
    msg = send(session, shop, "laxmi")
    pipeline.process_business(shop.id)
    assert transactions(session, shop) == []
    assert refreshed(session, msg).reply_text == f"[MOCK] {t.UNKNOWN_CUSTOMER}"


def test_reply_name_comes_from_customer_record_not_model_text(session, shop, lakshmi, extract):
    extract("credit", line(amount="2500", name="Lakshmi garu", native="లక్ష్మీ గారు"))
    msg = send(session, shop, "credit")
    pipeline.process_business(shop.id)
    reply = refreshed(session, msg).reply_text
    assert "లక్ష్మి కి" in reply  # stored spelling
    assert "లక్ష్మీ" not in reply and "గారు" not in reply


def test_extractor_failure_marks_failed_and_next_message_still_runs(session, shop, lakshmi, monkeypatch):
    class Boom:
        is_mock = True

        def extract(self, text):
            if text == "boom":
                raise TimeoutError("model timed out")
            return Extraction(lines=[line(amount="2500")])

    monkeypatch.setattr(pipeline, "get_extractor", Boom)
    now = datetime.now(UTC)
    failed = send(session, shop, "boom", received_at=now)
    ok = send(session, shop, "fine", received_at=now + timedelta(seconds=1))
    pipeline.process_business(shop.id)

    failed = refreshed(session, failed)
    assert (failed.status, failed.reply_text) == ("failed", f"[MOCK] {t.SEND_AGAIN}")
    assert "TimeoutError" in failed.error
    assert refreshed(session, ok).status == "done"
    assert session.scalar(select(func.count()).select_from(Transaction).where(Transaction.business_id == shop.id)) == 1
