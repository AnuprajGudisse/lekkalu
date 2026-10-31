# Copyright (c) 2026 Lekkalu
from app.ai.schemas import Extraction


class MockExtractor:
    """Canned extractions for tests. Replies built from it are labeled [MOCK]."""

    is_mock = True

    def __init__(self, responses: dict[str, Extraction] | None = None):
        self.responses = responses or {}

    def extract(self, text: str) -> Extraction:
        return self.responses.get(text, Extraction(lines=[]))
