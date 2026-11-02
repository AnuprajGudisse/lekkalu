# Copyright (c) 2026 Lekkalu
class MockTranscriber:
    """A fixed transcript for tests. Replies built from it are labeled [MOCK]."""

    is_mock = True

    def __init__(self, text: str = ""):
        self.text = text
        self.calls = 0

    def transcribe(self, wav: bytes, keywords: list[str]) -> str:
        self.calls += 1
        return self.text
