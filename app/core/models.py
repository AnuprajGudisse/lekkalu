# Copyright (c) 2026 Lekkalu
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (CheckConstraint("is_public_demo OR access_token IS NOT NULL", name="private_has_token"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    access_token: Mapped[str | None] = mapped_column(Text, unique=True)
    is_public_demo: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
