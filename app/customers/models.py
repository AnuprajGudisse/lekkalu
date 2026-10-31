# Copyright (c) 2026 Lekkalu
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("business_id", "normalized_name"),
        UniqueConstraint("business_id", "id"),  # target of transactions' same-business FK
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(Text)  # Latin; the identity
    name_native: Mapped[str | None] = mapped_column(Text)  # as spoken, for Telugu replies
    normalized_name: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
