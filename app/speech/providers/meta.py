# Copyright (c) 2026 Lekkalu
"""Muse Voice Transcribe through the Meta Model API. Request shape measured in spikes/stt_compare.py."""
import json

import httpx

from app.core.config import get_settings
from app.speech.services import TranscriptionError


class MetaTranscriber:
    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        if client is None:
            if not s.meta_api_key:
                raise TranscriptionError("META_API_KEY is not set")
            # retries=2 covers connection errors only, matching the extractor's retry on a dropped connection.
            client = httpx.Client(base_url=s.meta_api_base_url, timeout=s.model_timeout_s,
                                  headers={"Authorization": f"Bearer {s.meta_api_key}"},
                                  transport=httpx.HTTPTransport(retries=2))
        self.client = client
        self.model = s.meta_stt_model

    def transcribe(self, wav: bytes, keywords: list[str]) -> str:
        request = {"mode": "ENDPOINTING", "model": self.model, "audioEncoding": "WAV",
                   "languageBias": ["Telugu", "English"]}
        if keywords:
            request["keywords"] = keywords
        r = self.client.post("/asr/transcribe", files={
            "request": (None, json.dumps(request, ensure_ascii=False), "application/json"),
            "audio": ("audio.wav", wav, "audio/wav"),
        })
        r.raise_for_status()
        body = r.json()
        if "transcript" not in body and "turns" not in body:
            # A changed or error-shaped 200 must fail loudly, not pass as silence ("didn't understand").
            raise TranscriptionError(f"no transcript in Muse response; keys: {sorted(body)}")
        # ponytail: only single-turn clips were measured; fall back to the turns if the top level is empty.
        return body.get("transcript") or " ".join(t.get("transcript", "") for t in body.get("turns", [])).strip()
