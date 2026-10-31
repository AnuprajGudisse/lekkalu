# Copyright (c) 2026 Lekkalu
"""Message processing: claim, extract, route to the ledger, reply.

One message per business at a time, oldest first. Each message ends in a single DB
transaction holding the ledger write, the reply and the final status, so a crash
leaves either all of it or none of it; startup recovery re-runs the rest.
"""
import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import exists, select, text, update
from sqlalchemy.orm import Session

from app.ai.schemas import CUSTOMER_REQUIRED, TRANSACTION_INTENTS, Extraction, ExtractionError, to_paise
from app.ai.services import get_extractor
from app.core import database
from app.customers import services as customers
from app.customers.models import Customer
from app.ledger import services as ledger
from app.ledger.rules import derive_cost
from app.messaging import templates_te as t
from app.messaging.models import Message

log = logging.getLogger(__name__)

# ponytail: in-process locks assume one Uvicorn worker; use a Postgres advisory lock for more.
_locks: dict[int, threading.Lock] = {}


def process_business(business_id: int) -> None:
    lock = _locks.setdefault(business_id, threading.Lock())
    while True:
        if not lock.acquire(blocking=False):
            return  # the holder drains the queue
        try:
            while (message_id := claim_next(business_id)) is not None:
                process_message(message_id)
        finally:
            lock.release()
        # A message committed while the holder was finishing found the lock taken; pick it up.
        if not has_received(business_id):
            return


def claim_next(business_id: int) -> int | None:
    with database.SessionLocal() as s, s.begin():
        return s.scalar(
            text(
                "UPDATE messages SET status = 'processing' WHERE id = ("
                "  SELECT id FROM messages WHERE business_id = :b AND status = 'received'"
                "  ORDER BY received_at, id LIMIT 1"
                ") AND status = 'received' RETURNING id"
            ),
            {"b": business_id},
        )


def has_received(business_id: int) -> bool:
    with database.SessionLocal() as s:
        return s.scalar(
            select(exists().where(Message.business_id == business_id, Message.status == "received"))
        )


def recover() -> list[int]:
    """Startup only (single worker): anything still `processing` was interrupted."""
    with database.SessionLocal() as s, s.begin():
        s.execute(update(Message).where(Message.status == "processing").values(status="received"))
        return list(s.scalars(select(Message.business_id).where(Message.status == "received").distinct()))


def process_message(message_id: int) -> None:
    extractor = None
    try:
        with database.SessionLocal() as s:
            body = s.get(Message, message_id).body
        extractor = get_extractor()
        extraction = extractor.extract(body)  # model call holds no DB transaction
        with database.SessionLocal() as s, s.begin():
            msg = s.get(Message, message_id)
            msg.extraction = extraction.model_dump(mode="json")
            _finish(msg, route(s, msg, extraction), "done", extractor)
    except Exception as e:
        log.exception("message %s failed", message_id)
        # If the database itself is down this write fails too; the message stays `processing`
        # until startup recovery (no periodic sweep in the MVP).
        with database.SessionLocal() as s, s.begin():
            msg = s.get(Message, message_id)
            msg.error = f"{type(e).__name__}: {e}"[:2000]
            _finish(msg, t.SEND_AGAIN, "failed", extractor)


def _finish(msg: Message, reply: str, status: str, extractor) -> None:
    msg.reply_text = f"[MOCK] {reply}" if getattr(extractor, "is_mock", False) else reply
    msg.replied_at = datetime.now(UTC)
    msg.status = status


def route(s: Session, msg: Message, extraction: Extraction) -> str:
    """Phase 2 routing: one complete transaction is recorded; anything else gets a Telugu reply."""
    lines = extraction.lines
    if len(lines) > 1:
        return t.SEND_SEPARATELY
    if not lines or lines[0].intent not in TRANSACTION_INTENTS | {"query", "correction"}:
        return t.NOT_UNDERSTOOD
    line = lines[0]
    if line.intent not in TRANSACTION_INTENTS:
        return t.NOT_YET
    # Unknown stays unknown: ask, never guess. A number the model itself lists as missing is a guess.
    if line.amount_rupees is None or "amount_rupees" in line.missing_fields:
        return t.ASK_AMOUNT
    try:
        amount = to_paise(line.amount_rupees)
        cost = None
        if line.intent in ("sale", "credit_sale") and line.profit_rupees is not None:
            # to_paise rejects zero, but a stated zero profit is a real zero.
            profit = 0 if line.profit_rupees == 0 else to_paise(line.profit_rupees)
            cost = derive_cost(amount, profit)
    except (ExtractionError, ValueError):  # zero, negative or fractional paise; profit above amount
        return t.ASK_AMOUNT  # resending the same words would fail again, so ask instead

    customer = None
    if line.intent in CUSTOMER_REQUIRED | {"sale"} and (line.customer_name or line.customer_name_native):
        match = customers.find(s, business_id=msg.business_id, name=line.customer_name,
                               name_native=line.customer_name_native)
        if match.status == "matched":
            customer = s.get(Customer, match.customer_id)
    if line.intent in CUSTOMER_REQUIRED and customer is None:
        return t.UNKNOWN_CUSTOMER

    quantity = line.quantity if line.quantity and line.quantity > 0 else None
    tx = ledger.record(
        s, business_id=msg.business_id, source_message_id=msg.id, type=line.intent, amount_paise=amount,
        occurred_at=msg.received_at, customer_id=customer.id if customer else None, cost_paise=cost,
        item=line.item, item_native=line.item_native, quantity=quantity,
    ).transaction

    if tx.type in CUSTOMER_REQUIRED:
        name = customer.name_native or customer.name
        balance = ledger.customer_balance(s, customer_id=customer.id)
        render = t.credit_sale if tx.type == "credit_sale" else t.payment_received
        return render(name, tx.amount_paise, balance)
    return {"sale": t.sale, "purchase": t.purchase, "expense": t.expense}[tx.type](tx.amount_paise)
