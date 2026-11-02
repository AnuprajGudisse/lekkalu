# Copyright (c) 2026 Lekkalu
"""Tests run against lekkalu_test, built only by `alembic upgrade head`.

Each test runs inside one outer transaction that is rolled back, because the
ledger trigger blocks TRUNCATE.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import database
from app.core.config import get_settings
from app.core.models import Business
from app.customers.models import Customer
from app.messaging.models import Message


def alembic_config() -> Config:
    url = get_settings().test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set", returncode=2)
    cfg = Config("alembic.ini")
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def engine():
    cfg = alembic_config()
    # Rebuild from base so in-place edits to a migration are always what gets tested.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(cfg.attributes["url"])
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with engine.connect() as conn:
        outer = conn.begin()
        s = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            s.close()
            outer.rollback()


@pytest.fixture
def db(session, monkeypatch):
    """Point app code (pipeline, API) at the test connection; its commits become savepoint releases."""
    factory = sessionmaker(bind=session.connection(), join_transaction_mode="create_savepoint", expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    return factory


def make_business(session: Session, *, public: bool = False, **kw) -> Business:
    b = Business(
        name=kw.pop("name", "Test Saree Shop"),
        slug=kw.pop("slug", uuid4().hex),
        access_token=None if public else kw.pop("access_token", uuid4().hex),
        is_public_demo=public,
        **kw,
    )
    session.add(b)
    session.flush()
    return b


def make_customer(session: Session, business: Business, name: str = "Lakshmi", **kw) -> Customer:
    # Raw row for ledger tests; customer behaviour is tested through customers.services.
    c = Customer(business_id=business.id, name=name, normalized_name=name.casefold(), **kw)
    session.add(c)
    session.flush()
    return c


def make_message(session: Session, business: Business, *, received_at: datetime | None = None, **kw) -> Message:
    m = Message(
        business_id=business.id,
        channel=kw.pop("channel", "web"),
        external_message_id=kw.pop("external_message_id", uuid4().hex),
        received_at=received_at or datetime.now(UTC),
        kind=kw.pop("kind", "text"),
        body=kw.pop("body", "test"),
        **kw,
    )
    session.add(m)
    session.flush()
    return m
