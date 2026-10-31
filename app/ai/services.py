# Copyright (c) 2026 Lekkalu
from functools import lru_cache
from typing import Protocol

from app.ai.schemas import Extraction


class Extractor(Protocol):
    def extract(self, text: str) -> Extraction: ...


@lru_cache
def get_extractor() -> Extractor:
    from app.ai.providers.meta import MetaExtractor

    return MetaExtractor()
