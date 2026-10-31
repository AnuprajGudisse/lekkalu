# Copyright (c) 2026 Lekkalu
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("channel", "external_message_id"),
        UniqueConstraint("business_id", "id"),  # target of transactions' same-business FKs
        CheckConstraint("channel IN ('web', 'whatsapp')", name="channel"),
        CheckConstraint("kind IN ('text', 'audio')", name="kind"),
        CheckConstraint(
            "status IN ('received', 'processing', 'awaiting_clarification', 'expired', 'done', 'failed')",
            name="status",
        ),
        CheckConstraint(
            "status <> 'awaiting_clarification' OR clarification_expires_at IS NOT NULL",
            name="clarification_has_expiry",
        ),
        Index(None, "business_id", "status", "received_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("businesses.id"))
    channel: Mapped[str] = mapped_column(Text)
    external_message_id: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    transcript_te: Mapped[str | None] = mapped_column(Text)
    transcript_en: Mapped[str | None] = mapped_column(Text)
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default="received")
    clarification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_text: Mapped[str | None] = mapped_column(Text)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
