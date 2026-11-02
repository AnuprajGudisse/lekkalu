# Copyright (c) 2026 Lekkalu
"""Extraction contract. Validated before anything reaches the ledger."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Intent = Literal["sale", "credit_sale", "purchase", "expense", "payment_received", "query", "correction", "other"]
INTENTS = list(Intent.__args__)
TRANSACTION_INTENTS = {"sale", "credit_sale", "purchase", "expense", "payment_received"}
CUSTOMER_REQUIRED = {"credit_sale", "payment_received"}


class Line(BaseModel):
    intent: Intent
    # Before amount_rupees so the model writes the words first; checked by numbers_te.parse_amount.
    amount_words: str | None = None  # the words that state the amount, as written
    # Decimal, never float: rupee amounts parse exactly (only numbers past ~17 digits lose precision).
    amount_rupees: Decimal | None
    profit_rupees: Decimal | None
    quantity: int | None
    item: str | None  # English
    item_native: str | None  # as in the message (Telugu script when said in Telugu)
    customer_name: str | None  # Latin script
    customer_name_native: str | None  # as in the message
    missing_fields: list[str]


class Extraction(BaseModel):
    lines: list[Line]


class ExtractionError(Exception):
    """The model gave no usable extraction."""


def to_paise(rupees: Decimal) -> int:
    paise = rupees * 100
    if paise <= 0 or paise != paise.to_integral_value():
        raise ExtractionError(f"amount is not a positive whole number of paise: {rupees}")
    return int(paise)


def _nullable(t: str) -> dict:
    return {"anyOf": [{"type": t}, {"type": "null"}]}


_LINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(Line.model_fields),
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "amount_words": _nullable("string"),
        "amount_rupees": _nullable("number"),
        "profit_rupees": _nullable("number"),
        "quantity": _nullable("integer"),
        "item": _nullable("string"),
        "item_native": _nullable("string"),
        "customer_name": _nullable("string"),
        "customer_name_native": _nullable("string"),
        "missing_fields": {"type": "array", "items": {"type": "string"}},
    },
}

JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": _LINE_SCHEMA}},
}
