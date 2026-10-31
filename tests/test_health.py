# Copyright (c) 2026 Lekkalu
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core import database
from app.main import app

client = TestClient(app)


def test_health_reports_ok_when_database_answers():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_health_reports_503_when_database_is_unreachable(monkeypatch):
    dead = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1})
    monkeypatch.setattr(database, "engine", dead)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["db"] == "error"
