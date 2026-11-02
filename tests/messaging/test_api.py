# Copyright (c) 2026 Lekkalu
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai.providers.mock import MockExtractor
from app.ai.schemas import Extraction, Line
from app.core.config import get_settings
from app.customers import services as customers
from app.ledger.models import Transaction
from app.main import app
from app.messaging import views
from app.messaging.models import Message
from app.processing import pipeline
from app.speech import audio
from app.speech.providers.mock import MockTranscriber
from tests.conftest import make_business

client = TestClient(app)  # no `with`: lifespan recovery stays out of API tests
TEXT = "లక్ష్మి రెండు చీరలు తీసుకుంది, రెండు వేల ఐదు వందలు, తర్వాత ఇస్తుంది"


@pytest.fixture
def demo(session, db, monkeypatch):
    shop = make_business(session, public=True)
    customers.create(session, business_id=shop.id, name="Lakshmi", name_native="లక్ష్మి")
    credit = Line(intent="credit_sale", amount_rupees=2500, amount_words="రెండు వేల ఐదు వందలు", profit_rupees=None, quantity=2, item="saree",
                  item_native="చీరలు", customer_name="Lakshmi", customer_name_native="లక్ష్మి", missing_fields=[])
    monkeypatch.setattr(pipeline, "get_extractor", lambda: MockExtractor({TEXT: Extraction(lines=[credit])}))
    return shop


def count(session, model, business):
    return session.scalar(select(func.count()).select_from(model).where(model.business_id == business.id))


def test_same_client_message_id_twice_creates_one_message_and_one_transaction(session, demo):
    body = {"client_message_id": str(uuid4()), "text": TEXT}
    first = client.post(f"/api/{demo.slug}/messages", json=body)
    second = client.post(f"/api/{demo.slug}/messages", json=body)
    assert (first.status_code, second.status_code) == (202, 202)
    assert first.json() == second.json()
    assert count(session, Message, demo) == 1
    assert count(session, Transaction, demo) == 1

    [m] = client.get(f"/api/{demo.slug}/messages").json()
    assert m["status"] == "done"
    assert "₹2,500" in m["reply_text"]
    assert client.get(f"/api/{demo.slug}/messages", params={"after": m["id"]}).json() == []


def test_public_demo_needs_no_token(demo):
    assert client.get(f"/c/{demo.slug}").status_code == 200


def test_private_business_requires_token(session, db):
    shop = make_business(session, access_token="secret-token")
    body = {"client_message_id": str(uuid4()), "text": "hi"}
    assert client.get(f"/c/{shop.slug}").status_code == 404
    assert client.get(f"/c/{shop.slug}", params={"t": "wrong"}).status_code == 404
    assert client.get(f"/c/{shop.slug}", params={"t": "secret-token"}).status_code == 200
    assert client.post(f"/api/{shop.slug}/messages", json=body).status_code == 404
    assert client.get(f"/api/{shop.slug}/messages", headers={"X-Access-Token": "secret-token"}).status_code == 200


def test_unknown_slug_is_404(db):
    assert client.get("/c/no-such-shop").status_code == 404


def test_client_message_id_reused_on_other_business_is_409(session, demo):
    other = make_business(session, public=True)
    body = {"client_message_id": str(uuid4()), "text": TEXT}
    assert client.post(f"/api/{demo.slug}/messages", json=body).status_code == 202
    assert client.post(f"/api/{other.slug}/messages", json=body).status_code == 409


def test_blank_text_is_rejected(demo):
    body = {"client_message_id": str(uuid4()), "text": "   "}
    assert client.post(f"/api/{demo.slug}/messages", json=body).status_code == 422


def test_messages_list_only_shows_own_business(session, demo):
    other = make_business(session, public=True)
    client.post(f"/api/{demo.slug}/messages", json={"client_message_id": str(uuid4()), "text": TEXT})
    assert client.get(f"/api/{other.slug}/messages").json() == []


# --- voice notes ---

@pytest.fixture
def voice(demo, tmp_path, monkeypatch):
    """Audio lands in tmp_path; ffmpeg and Muse Voice Transcribe are replaced; the transcript is TEXT."""
    monkeypatch.setattr(get_settings(), "audio_dir", tmp_path)
    monkeypatch.setattr(audio, "to_wav", lambda path: path.read_bytes())
    monkeypatch.setattr(pipeline, "get_transcriber", lambda: MockTranscriber(TEXT))
    return tmp_path


def post_audio(slug, cid, data=b"webm-bytes", **kw):
    return client.post(f"/api/{slug}/messages/audio", data={"client_message_id": cid},
                       files={"audio": ("note.webm", data, "audio/webm;codecs=opus")}, **kw)


def test_same_voice_note_twice_stores_one_message_one_file_and_one_transaction(session, demo, voice):
    cid = str(uuid4())
    first, second = post_audio(demo.slug, cid), post_audio(demo.slug, cid)
    assert (first.status_code, second.status_code) == (202, 202)
    assert first.json() == second.json()
    assert count(session, Message, demo) == 1
    assert count(session, Transaction, demo) == 1
    assert [p.name for p in voice.rglob("*") if p.is_file()] == [f"{cid}.audio"]  # no .part left behind

    [m] = client.get(f"/api/{demo.slug}/messages").json()
    assert (m["kind"], m["body"], m["transcript"], m["status"]) == ("audio", None, TEXT, "done")
    assert "₹2,500" in m["reply_text"]


def test_voice_note_for_private_business_needs_its_token(session, db, voice):
    shop = make_business(session, access_token="secret-token")
    assert post_audio(shop.slug, str(uuid4())).status_code == 404
    assert post_audio(shop.slug, str(uuid4()), headers={"X-Access-Token": "secret-token"}).status_code == 202


def test_oversized_voice_note_is_refused_and_not_stored(session, demo, voice):
    big = b"x" * (views.MAX_AUDIO_BYTES + 1)
    assert post_audio(demo.slug, str(uuid4()), big).status_code == 413
    assert count(session, Message, demo) == 0
    assert not any(voice.rglob("*.audio"))


def test_empty_voice_note_is_refused(session, demo, voice):
    assert post_audio(demo.slug, str(uuid4()), b"").status_code == 422
    assert count(session, Message, demo) == 0


def test_voice_note_id_already_used_by_another_business_conflicts(session, demo, voice):
    other = make_business(session, public=True)
    cid = str(uuid4())
    assert post_audio(demo.slug, cid).status_code == 202
    assert post_audio(other.slug, cid).status_code == 409
    assert count(session, Message, other) == 0
