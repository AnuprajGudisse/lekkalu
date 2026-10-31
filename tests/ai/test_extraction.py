# Copyright (c) 2026 Lekkalu
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.providers.meta import MetaExtractor
from app.ai.schemas import ExtractionError, to_paise

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "meta_spark"


def stub_client(content: str | None):
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")])
    create = lambda **kw: response  # noqa: E731
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def recorded(name: str) -> str:
    return json.loads((FIXTURES / f"extraction_lines_{name}.json").read_text())["content"]


def test_meta_extractor_parses_recorded_credit_sale():
    [line] = MetaExtractor(client=stub_client(recorded("credit_sale"))).extract("ignored").lines
    assert line.intent == "credit_sale"
    assert to_paise(line.amount_rupees) == 250000
    assert (line.customer_name, line.customer_name_native) == ("Lakshmi", "లక్ష్మి")
    assert line.quantity == 2


def test_meta_extractor_keeps_two_recorded_transactions_apart():
    lines = MetaExtractor(client=stub_client(recorded("two_transactions"))).extract("ignored").lines
    assert [line.intent for line in lines] == ["sale", "expense"]


def test_to_paise_is_exact_and_rejects_fractional_paise_and_non_positive():
    assert to_paise(Decimal("2500")) == 250000
    assert to_paise(Decimal("1500.5")) == 150050
    for bad in ("0", "-10", "0.001"):
        with pytest.raises(ExtractionError):
            to_paise(Decimal(bad))


def test_empty_model_content_is_a_failure():
    with pytest.raises(ExtractionError, match="empty"):
        MetaExtractor(client=stub_client(None)).extract("x")
