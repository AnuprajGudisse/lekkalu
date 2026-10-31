# Copyright (c) 2026 Lekkalu
"""Muse Spark extraction through the Meta Model API (OpenAI-compatible)."""
from openai import OpenAI

from app.ai.prompts import EXTRACTION_SYSTEM
from app.ai.schemas import JSON_SCHEMA, Extraction, ExtractionError
from app.core.config import get_settings


class MetaExtractor:
    def __init__(self, client: OpenAI | None = None):
        s = get_settings()
        if client is None:
            if not s.meta_api_key:
                raise ExtractionError("META_API_KEY is not set")
            # The SDK default timeout is 10 minutes; always pass ours. Retries (connection errors,
            # 429, 5xx only) can stretch one message to ~90 s; accepted per the spec.
            client = OpenAI(base_url=s.meta_api_base_url, api_key=s.meta_api_key,
                            timeout=s.model_timeout_s, max_retries=2)
        self.client = client
        self.model = s.meta_model

    def extract(self, text: str) -> Extraction:
        return Extraction.model_validate_json(self.complete(text))

    def complete(self, text: str) -> str:
        """Raw JSON content from the model."""
        r = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,  # reasoning tokens count against this; small limits return no content
            reasoning_effort="minimal",  # same accuracy as default on the spikes, ~5x faster
            messages=[{"role": "system", "content": EXTRACTION_SYSTEM}, {"role": "user", "content": text}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "extraction", "strict": True, "schema": JSON_SCHEMA}},
        )
        choice = r.choices[0]
        if not choice.message.content:
            raise ExtractionError(f"empty model content (finish_reason={choice.finish_reason})")
        return choice.message.content
