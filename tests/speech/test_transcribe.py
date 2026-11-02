# Copyright (c) 2026 Lekkalu
import json
from pathlib import Path

import httpx
import pytest

from app.speech.providers.meta import MetaTranscriber
from app.speech.services import TranscriptionError

RECORDED = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "meta_stt" / "credit_sale.json")
                      .read_text())


def transcriber(seen: list, response: dict = RECORDED, status: int = 200) -> MetaTranscriber:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=response)
    return MetaTranscriber(client=httpx.Client(base_url="https://api.test/v1", transport=httpx.MockTransport(handle)))


def request_json(request: httpx.Request) -> dict:
    """The `request` part of the multipart body."""
    body = request.read().decode()
    part = next(p for p in body.split("--") if 'name="request"' in p)
    return json.loads(part.split("\r\n\r\n", 1)[1].rsplit("\r\n", 1)[0])


def test_recorded_muse_response_returns_its_transcript_with_telugu_and_english_bias():
    seen = []
    text = transcriber(seen).transcribe(b"RIFF....", keywords=[])
    assert text == RECORDED["transcript"]
    [req] = seen
    assert req.url.path == "/v1/asr/transcribe"
    sent = request_json(req)
    assert sent["languageBias"] == ["Telugu", "English"]
    assert sent["audioEncoding"] == "WAV"
    assert "keywords" not in sent  # off by default
    assert b'name="audio"' in req.read()


def test_keywords_are_sent_when_given():
    seen = []
    transcriber(seen).transcribe(b"RIFF....", keywords=["చీర", "saree"])
    assert request_json(seen[0])["keywords"] == ["చీర", "saree"]


def test_empty_top_level_transcript_falls_back_to_turns():
    response = {"transcript": "", "turns": [{"transcript": "లక్ష్మి"}, {"transcript": "వెయ్యి ఇచ్చింది"}]}
    assert transcriber([], response).transcribe(b"", keywords=[]) == "లక్ష్మి వెయ్యి ఇచ్చింది"


def test_success_status_without_a_transcript_fails_instead_of_passing_as_silence():
    with pytest.raises(TranscriptionError, match="error"):
        transcriber([], {"error": {"message": "quota"}}).transcribe(b"", keywords=[])


def test_http_error_fails_loudly():
    with pytest.raises(httpx.HTTPStatusError):
        transcriber([], {"error": "bad"}, status=500).transcribe(b"", keywords=[])
