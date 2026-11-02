# Copyright (c) 2026 Lekkalu
"""Spoken amounts (Telugu, English, digits) to paise.

Strict: any word it does not know makes the whole amount unknown (None), so the caller
asks instead of guessing. Built against real Muse Voice Transcribe output (spikes/RESULTS.md):
case endings (వేయి రూపాయలకు), repeats in two spellings (వెయ్యి వేయి), words run together (రెండువేలు).
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

_UNITS = {
    "ఒకటి": 1, "ఒక్కటి": 1, "ఒక": 1, "ఒక్క": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "అయిదు": 5,
    "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10, "పదకొండు": 11, "పన్నెండు": 12,
    "పదమూడు": 13, "పద్నాలుగు": 14, "పదిహేను": 15, "పదహారు": 16, "పదిహేడు": 17, "పద్దెనిమిది": 18,
    "పంతొమ్మిది": 19, "ఇరవై": 20, "ఇరువై": 20, "పాతిక": 25, "ముప్పై": 30, "ముప్ఫై": 30, "ముప్పయి": 30,
    "నలభై": 40, "నలబై": 40, "యాభై": 50, "ఏభై": 50, "యాబై": 50, "అరవై": 60, "డెబ్బై": 70, "డబ్బై": 70,
    "ఎనభై": 80, "ఎనబై": 80, "తొంభై": 90, "తొంబై": 90,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MULTIPLIERS = {
    "వంద": 100, "వందలు": 100, "వందల": 100, "నూట": 100, "నూరు": 100, "hundred": 100, "hundreds": 100,
    "వెయ్యి": 1000, "వేయి": 1000, "వేలు": 1000, "వేల": 1000, "thousand": 1000, "thousands": 1000, "k": 1000,
    "లక్ష": 100000, "లక్షలు": 100000, "లక్షల": 100000, "lakh": 100000, "lakhs": 100000, "lac": 100000,
}
_VOCAB = ({k: ("num", Decimal(v)) for k, v in _UNITS.items()}
          | {k: ("mul", Decimal(v)) for k, v in _MULTIPLIERS.items()}
          | {"అర": ("half", None)})
_KEYS = sorted(_VOCAB, key=len, reverse=True)  # longest prefix first
_CASE_ENDINGS = {"కు", "కి", "లకు", "లకి"}  # పాతిక వందలకు, వేయి రూపాయలకు
_SKIP_PREFIXES = ("రూపా", "రూపీ", "rupee", "rs")
_DIGITS = re.compile(r"(\d+(?:\.\d+)?)(k)?(?:కు|కి)?")
# ponytail: పావు (quarter) is left out; an amount using it asks again, the safe failure.


def parse_amount(text: str | None) -> int | None:
    """Paise, or None when any part of the text is not a number word."""
    tokens = _tokens(text or "")
    if not tokens:
        return None
    total = current = Decimal(0)
    prev = None
    last_big = None  # the last thousand/lakh applied; each must be smaller than the one before
    for tok in tokens:
        # ponytail: STT repeats words ("రెండు రెండు", "వెయ్యి వేయి"), so equal neighbours collapse;
        # a genuinely repeated number cannot be said this way, fine for spoken money.
        if tok == prev:
            continue
        kind, value = tok
        if kind == "num":
            # A number may follow another only as tens then units ("ఇరవై ఐదు"), never "రెండు ఐదు" or "300 200".
            if prev and prev[0] == "num" and not (prev[1] >= 20 and prev[1] % 10 == 0 and value < 10):
                return None
            if prev and prev[0] == "mul" and value >= prev[1]:
                return None  # "వెయ్యి 2000": a number after a multiplier is smaller than it
            current += value
        elif kind == "half":
            if prev and prev[0] == "mul":  # వెయ్యిన్నర, నూటన్నర: half of the multiplier just said
                if prev[1] == 100:
                    current += 50
                else:
                    total += prev[1] / 2
            else:  # రెండున్నర వేలు, అర లక్ష
                current += Decimal("0.5")
        elif value == 100:
            if current >= 100:
                return None  # "రెండు వందల ఐదు వందలు"
            current = (current or 1) * 100
        else:
            if last_big is not None and value >= last_big:
                return None  # "ఐదు వేల రెండు వేలు", or a whole phrase said twice
            total += (current or 1) * value
            current = 0
            last_big = value
        prev = tok
    paise = (total + current) * 100
    if paise <= 0 or paise != paise.to_integral_value():
        return None
    return int(paise)


def _tokens(text: str) -> list[tuple] | None:
    s = unicodedata.normalize("NFC", text).casefold()
    s = s.replace("‌", "").replace("‍", "").replace("/-", "").replace(",", "").replace("₹", " ")
    s = s.replace("రూ.", " ")
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)  # keep the decimal point in 2.5k
    s = re.sub(r"[?!:;()\"'।-]", " ", s)
    s = s.replace("ొంద", "ు వంద").replace("న్నర", " అర")  # ఐదొందలు, రెండున్నర / వెయ్యిన్నర
    tokens = []
    for word in s.split():
        if word.startswith(_SKIP_PREFIXES) or word == "and":
            continue
        if m := _DIGITS.fullmatch(word):
            try:
                tokens.append(("num", Decimal(m[1])))
            except InvalidOperation:
                return None
            if m[2]:
                tokens.append(_VOCAB["k"])
            continue
        rest = word
        while rest:
            if rest != word and rest in _CASE_ENDINGS:
                break
            key = next((k for k in _KEYS if rest.startswith(k)), None)
            if key is None:
                return None
            tokens.append(_VOCAB[key])
            rest = rest[len(key):]
    return tokens
