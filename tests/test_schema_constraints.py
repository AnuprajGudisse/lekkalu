# Copyright (c) 2026 Lekkalu
"""Constraints on businesses and messages."""
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.models import Business
from app.messaging.models import Message
from tests.conftest import make_business, make_message


def flush_rejected(session, match: str, obj):
    with pytest.raises(DBAPIError, match=match), session.begin_nested():
        session.add(obj)
        session.flush()


def test_private_business_requires_token(session):
    flush_rejected(session, "private_has_token", Business(name="x", slug="no-token", access_token=None))


def test_public_demo_needs_no_token(session):
    assert make_business(session, public=True).access_token is None


def test_duplicate_channel_message_id_rejected(session):
    shop = make_business(session)
    first = make_message(session, shop)
    duplicate = Message(
        business_id=shop.id,
        channel=first.channel,
        external_message_id=first.external_message_id,
        received_at=datetime.now(UTC),
        kind="text",
    )
    flush_rejected(session, "uq_messages_channel_external_message_id", duplicate)


def test_same_message_id_on_another_channel_accepted(session):
    shop = make_business(session)
    first = make_message(session, shop)
    make_message(session, shop, channel="whatsapp", external_message_id=first.external_message_id)


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [("channel", "sms", "ck_messages_channel"), ("kind", "video", "ck_messages_kind"), ("status", "lost", "ck_messages_status")],
)
def test_message_enums_rejected(session, field, value, constraint):
    shop = make_business(session)
    fields = dict(business_id=shop.id, channel="web", external_message_id="m-1", received_at=datetime.now(UTC), kind="text")
    fields[field] = value
    flush_rejected(session, constraint, Message(**fields))


def test_awaiting_clarification_requires_expiry(session):
    shop = make_business(session)
    msg = Message(
        business_id=shop.id,
        channel="web",
        external_message_id="m-2",
        received_at=datetime.now(UTC),
        kind="text",
        status="awaiting_clarification",
    )
    flush_rejected(session, "clarification_has_expiry", msg)
