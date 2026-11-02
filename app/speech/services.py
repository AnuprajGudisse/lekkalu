# Copyright (c) 2026 Lekkalu
from functools import lru_cache
from typing import Protocol


class TranscriptionError(Exception):
    """Speech-to-text gave no usable transcript."""


class Transcriber(Protocol):
    def transcribe(self, wav: bytes, keywords: list[str]) -> str: ...


@lru_cache
def get_transcriber() -> Transcriber:
    from app.speech.providers.meta import MetaTranscriber

    return MetaTranscriber()
