# Copyright (c) 2026 Lekkalu
import pytest

from app.speech.numbers_te import parse_amount


@pytest.mark.parametrize("text", [
    # done-when: all five resolve to ₹2,500
    "రెండు వేల ఐదు వందలు", "two thousand five hundred", "పాతిక వందలు", "2.5k", "2500",
    # other ways of saying it
    "రెండున్నర వేలు", "two thousand and five hundred", "twenty five hundred", "₹2,500/-", "రూ.2500",
    "2 వేల 500", "రెండు వేల, ఐదు వందలు",
    # real Muse Voice Transcribe output (spike 02, 07)
    "రెండు రెండు వేల ఐదువందలు.", "పాతిక వందల", "పాతిక వందలకు",
])
def test_two_thousand_five_hundred(text):
    assert parse_amount(text) == 250000


@pytest.mark.parametrize("text, paise", [
    # spike transcripts (reference, Muse, Sarvam) as written
    ("వెయ్యి రూపాయలకు", 100000),
    ("వేయి రూపాయలకు", 100000),
    ("వెయ్యి వేయి రూపాయలు", 100000),
    ("పదిహేను వేలు", 1500000),
    ("నూట యాభై రూపాయలు", 15000),
    ("నూటయాభై", 15000),
    ("₹150", 15000),
    ("Three thousand rupees", 300000),
    ("3000 రూపీస్", 300000),
    ("రెండువేలు", 200000),
    ("పదిహేను వందలు", 150000),
    ("fifteen hundred", 150000),
    ("రెండు వందలు", 20000),
    # forms Amma may use
    ("ఒక లక్ష", 10000000),
    ("1,00,000", 10000000),
    ("అర లక్ష", 5000000),
    ("ఐదొందలు", 50000),
    ("వెయ్యిన్నర", 150000),
    ("నూటన్నర", 15000),
    ("15 వేలు", 1500000),
    ("ఇరవై ఐదు", 2500),
    ("రెండు‌వేలు", 200000),  # zero-width non-joiner inside the word
    ("99.50", 9950),
    ("ఒక లక్ష యాభై వేలు", 15000000),  # lakh then thousand is fine
    ("two thousand five hundred fifty", 255000),
])
def test_amounts(text, paise):
    assert parse_amount(text) == paise


@pytest.mark.parametrize("text", [
    "పదిహేనుంహేనువేలు",  # garbled Muse output (spike 04, keywords on)
    None, "", "రూపాయలు", "డబ్బులు", "0",
    "రెండు ఐదు",  # two digits said in a row is not an amount
    "2500.005",  # fractional paise
    "రెండు వేలు కాదు పదిహేను వందలు",  # a sentence, not an amount
    # malformed sequences: strict means None, not a sum
    "300 200", "2 500", "ఐదు వేల రెండు వేలు", "రెండు వేలు రెండు వేలు", "రెండు వందల ఐదు వందలు", "వెయ్యి 2000",
])
def test_unresolvable_is_none(text):
    assert parse_amount(text) is None
