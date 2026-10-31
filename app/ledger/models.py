# Copyright (c) 2026 Lekkalu
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ACTIVE = text("voided_at IS NULL")


class Transaction(Base):
    """Immutable ledger row.

    A trigger allows exactly one UPDATE: setting the void link from NULL. voided_at,
    voided_by_message_id and (for corrections) replaced_by_id must be set in that same
    UPDATE; a link added later is rejected.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("source_message_id", "line_no"),
        UniqueConstraint("business_id", "id"),  # target of the same-business replaced_by FK
        CheckConstraint(
            "type IN ('sale', 'credit_sale', 'purchase', 'expense', 'payment_received')", name="type"
        ),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        CheckConstraint("cost_paise IS NULL OR cost_paise >= 0", name="cost_non_negative"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint("replaced_by_id IS NULL OR voided_at IS NOT NULL", name="replaced_implies_voided"),
        CheckConstraint("replaced_by_id <> id", name="not_replaced_by_self"),
        CheckConstraint("(voided_at IS NULL) = (voided_by_message_id IS NULL)", name="void_link_complete"),
        CheckConstraint(
            "type NOT IN ('credit_sale', 'payment_received') OR customer_id IS NOT NULL", name="credit_has_customer"
        ),
        CheckConstraint("cost_paise IS NULL OR type IN ('sale', 'credit_sale')", name="cost_only_on_sales"),
        # Customer, messages and replacement must belong to the same business as the row.
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.id"]),
        ForeignKeyConstraint(["business_id", "source_message_id"], ["messages.business_id", "messages.id"]),
        ForeignKeyConstraint(["business_id", "voided_by_message_id"], ["messages.business_id", "messages.id"]),
        ForeignKeyConstraint(["business_id", "replaced_by_id"], ["transactions.business_id", "transactions.id"]),
        Index("ix_transactions_active_business_occurred", "business_id", "occurred_at", postgresql_where=ACTIVE),
        Index("ix_transactions_active_customer", "customer_id", postgresql_where=ACTIVE),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("businesses.id"))
    customer_id: Mapped[int | None] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    line_no: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    type: Mapped[str] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    cost_paise: Mapped[int | None] = mapped_column(BigInteger)  # NULL = unknown (never written as 0); 0 is a real zero cost
    item: Mapped[str | None] = mapped_column(Text)  # English
    item_native: Mapped[str | None] = mapped_column(Text)  # as spoken
    quantity: Mapped[int | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_message_id: Mapped[int | None] = mapped_column(BigInteger)
    replaced_by_id: Mapped[int | None] = mapped_column(BigInteger)
    correction_reason: Mapped[str | None] = mapped_column(Text)
