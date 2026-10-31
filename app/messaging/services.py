# Copyright (c) 2026 Lekkalu
import secrets

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.models import Business
from app.messaging.models import Message


class MessageConflict(Exception):
    """The client message id already belongs to another business."""


def resolve_business(session: Session, slug: str, token: str | None) -> Business | None:
    b = session.scalars(select(Business).where(Business.slug == slug)).one_or_none()
    if b is None or b.is_public_demo:
        return b
    if token and secrets.compare_digest(token.encode(), b.access_token.encode()):
        return b
    return None


def store_message(session: Session, *, business_id: int, client_message_id: str, text: str) -> Message:
    """Insert once per (channel, client id); a resend returns the stored message."""
    session.execute(
        insert(Message)
        .values(business_id=business_id, channel="web", external_message_id=client_message_id,
                received_at=func.now(), kind="text", body=text)
        .on_conflict_do_nothing(index_elements=["channel", "external_message_id"])
    )
    msg = session.scalars(
        select(Message).where(Message.channel == "web", Message.external_message_id == client_message_id)
    ).one()
    if msg.business_id != business_id:
        raise MessageConflict(client_message_id)
    return msg


def list_messages(session: Session, *, business_id: int, after: int | None) -> list[Message]:
    q = select(Message).where(Message.business_id == business_id)
    if after is None:
        return list(reversed(session.scalars(q.order_by(Message.id.desc()).limit(50)).all()))
    return list(session.scalars(q.where(Message.id > after).order_by(Message.id).limit(200)))
