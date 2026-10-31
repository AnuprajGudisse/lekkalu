# Copyright (c) 2026 Lekkalu
"""Customer lookup. Services flush, never commit. Never imports ledger."""
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.customers.models import Customer
from app.customers.schemas import DuplicateCustomer, MatchResult

HONORIFICS = {"garu", "gaaru", "గారు", "amma", "అమ్మ"}
# Speech models alternate long and short vowel signs (లక్ష్మీ / లక్ష్మి); fold to short.
VOWEL_FOLD = str.maketrans({"ీ": "ి", "ూ": "ు"})
# Spec said 0.8, but "Laxmi" vs "Lakshmi" scores 0.67 and must ask. A fuzzy hit only asks, so err low.
FUZZY_RATIO = 0.6


def _is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P")


def normalize(name: str) -> str:
    words = unicodedata.normalize("NFC", name).casefold().translate(VOWEL_FOLD).split()
    words = ["".join(ch for ch in w if not _is_punct(ch)) for w in words]
    words = [w for w in words if w]
    while len(words) > 1 and words[-1] in HONORIFICS:
        words.pop()
    return " ".join(words)


def find(session: Session, *, business_id: int, name: str | None, name_native: str | None = None) -> MatchResult:
    keys = {k for k in (normalize(n) for n in (name, name_native) if n) if k}
    if not keys:
        return MatchResult(status="not_found")
    # ponytail: loads every customer of the business; a shop has dozens, index if it ever has thousands.
    customers = session.scalars(select(Customer).where(Customer.business_id == business_id)).all()

    exact = {c.id for c in customers if keys & {c.normalized_name, *c.aliases}}
    if len(exact) == 1:
        return MatchResult(status="matched", customer_id=exact.pop())
    if exact:
        return MatchResult(status="ambiguous", candidate_ids=sorted(exact))

    fuzzy = sorted(
        c.id
        for c in customers
        if any(SequenceMatcher(None, k, n).ratio() >= FUZZY_RATIO for k in keys for n in (c.normalized_name, *c.aliases))
    )
    if fuzzy:
        return MatchResult(status="ambiguous", candidate_ids=fuzzy)
    return MatchResult(status="not_found")


def create(session: Session, *, business_id: int, name: str, name_native: str | None = None) -> Customer:
    normalized = normalize(name)
    if not normalized:
        raise ValueError("customer name is empty")
    native = normalize(name_native) if name_native else ""
    customer = Customer(
        business_id=business_id,
        name=name.strip(),
        name_native=name_native.strip() if name_native else None,
        normalized_name=normalized,
        aliases=[native] if native and native != normalized else [],
    )
    try:
        with session.begin_nested():
            session.add(customer)
    except IntegrityError as e:
        if "uq_customers_business_id_normalized_name" not in str(e.orig):
            raise
        raise DuplicateCustomer(normalized) from e
    return customer


def add_alias(session: Session, *, customer_id: int, alias: str) -> None:
    customer = session.get(Customer, customer_id)
    a = normalize(alias)
    if a and a != customer.normalized_name and a not in customer.aliases:
        customer.aliases = [*customer.aliases, a]
        session.flush()
