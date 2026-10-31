# Copyright (c) 2026 Lekkalu
"""Spike: Muse Spark structured extraction and tool choice.

Usage: uv run python spikes/spark_extract.py
Reads eval/samples.json and spikes/out/stt/transcripts.json (from stt_compare.py).
Writes raw responses and a summary to spikes/out/spark/.
"""
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
import env  # noqa: E402

env.load()

from openai import BadRequestError, OpenAI  # noqa: E402
from pydantic import BaseModel, ValidationError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spikes" / "out" / "spark"
MODEL = os.environ.get("META_MODEL", "muse-spark-1.3")
client = OpenAI(base_url=os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1"),
                api_key=os.environ["META_API_KEY"], timeout=30, max_retries=0)

INTENTS = ["sale", "credit_sale", "purchase", "expense", "payment_received", "query", "correction", "other"]


def nullable(t: str) -> dict:
    return {"anyOf": [{"type": t}, {"type": "null"}]}


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "amount_rupees", "profit_rupees", "quantity", "item", "customer_name", "missing_fields"],
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "amount_rupees": nullable("number"),
        "profit_rupees": nullable("number"),
        "quantity": nullable("integer"),
        "item": nullable("string"),
        "customer_name": nullable("string"),
        "missing_fields": {"type": "array", "items": {"type": "string"}},
    },
}


class Extraction(BaseModel):
    intent: Literal["sale", "credit_sale", "purchase", "expense", "payment_received", "query", "correction", "other"]
    amount_rupees: float | None
    profit_rupees: float | None
    quantity: int | None
    item: str | None
    customer_name: str | None
    missing_fields: list[str]


SYSTEM = (
    "You extract one bookkeeping record from a message sent by a Telugu-speaking saree shop owner. "
    "The message may be Telugu, English, or mixed, and may contain speech-recognition errors such as repeated "
    "or misspelled words. Intents: sale (customer paid now), credit_sale (customer took goods and pays later), "
    "purchase (owner bought stock), expense (other business cost), payment_received (customer paid back credit), "
    "query (owner asks a question), correction (owner says a previous entry was wrong), other. "
    "amount_rupees is the total money of the transaction as a number; for a correction it is the corrected amount. "
    "profit_rupees only if the owner states it. Never guess: use null for anything not said, and list missing "
    "required fields (amount_rupees for any transaction; customer_name for credit_sale and payment_received) "
    "in missing_fields."
)

# Name variants for scoring only (script and spelling differences are not extraction errors).
NAMES = {
    "లక్ష్మి": {"లక్ష్మి", "లక్ష్మీ", "lakshmi", "laxmi"},
    "సుజాత": {"సుజాత", "sujatha", "sujata"},
    "పద్మ": {"పద్మ", "padma"},
}

strict = True


def extract(text: str, effort: str | None) -> dict:
    global strict
    kwargs = {"reasoning_effort": effort} if effort else {}
    for _ in range(2):
        start = time.perf_counter()
        try:
            r = client.chat.completions.create(
                model=MODEL, max_tokens=4000,
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "extraction", "strict": strict, "schema": SCHEMA}},
                **kwargs)
        except BadRequestError as e:
            if strict:
                print(f"strict schema rejected, retrying non-strict: {str(e)[:200]}")
                strict = False
                continue
            return {"error": f"400: {str(e)[:300]}"}
        elapsed = time.perf_counter() - start
        choice = r.choices[0]
        details = r.usage.completion_tokens_details if r.usage else None
        result = {"latency_s": round(elapsed, 2), "finish": choice.finish_reason,
                  "reasoning_tokens": getattr(details, "reasoning_tokens", None),
                  "content": choice.message.content}
        try:
            result["parsed"] = Extraction.model_validate_json(choice.message.content or "").model_dump()
        except ValidationError as e:
            result["error"] = f"parse: {str(e)[:300]}"
        return result
    return {"error": "unreachable"}


def name_ok(got: str | None, expected: str | None) -> bool:
    if expected is None:
        return got is None
    got = (got or "").strip().lower().replace(" garu", "").replace(" గారు", "")
    return got in NAMES.get(expected, {expected})


def score(parsed: dict, exp: dict) -> dict:
    s = {"intent": parsed["intent"] == exp["intent"]}
    s["amount"] = parsed["amount_rupees"] == exp.get("amount_rupees")
    s["customer"] = name_ok(parsed["customer_name"], exp.get("customer"))
    if "quantity" in exp:
        s["quantity"] = parsed["quantity"] == exp["quantity"]
    return s


def run_extraction() -> dict:
    samples = json.loads((ROOT / "eval" / "samples.json").read_text())
    transcripts = json.loads((ROOT / "spikes" / "out" / "stt" / "transcripts.json").read_text())
    configs = [("reference", None), ("muse", None), ("muse_kw", None), ("sarvam_en", None),
               ("reference", "low"), ("reference", "minimal")]
    jobs = []
    for source, effort in configs:
        for s in samples:
            text = s["reference_text"] if source == "reference" else transcripts[s["id"]][source]
            jobs.append((source, effort, s, text))

    extract(samples[0]["reference_text"], None)  # settles strict vs non-strict before going parallel
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda j: extract(j[3], j[1]), jobs))

    summary = {}
    for (source, effort, s, text), res in zip(jobs, results):
        key = f"{source}@{effort or 'default'}"
        (OUT / f"{key}_{s['id']}.json").write_text(json.dumps({"input": text, **res}, ensure_ascii=False, indent=2))
        row = summary.setdefault(key, {"n": 0, "failures": 0, "checks": {}, "latency": [], "reasoning": [], "misses": []})
        row["n"] += 1
        if "parsed" not in res:
            row["failures"] += 1
            row["misses"].append(f"{s['id']}: {res.get('error')}")
            continue
        row["latency"].append(res["latency_s"])
        if res["reasoning_tokens"] is not None:
            row["reasoning"].append(res["reasoning_tokens"])
        for check, ok in score(res["parsed"], s["expected"]).items():
            c = row["checks"].setdefault(check, [0, 0])
            c[0] += ok
            c[1] += 1
            if not ok:
                p = res["parsed"]
                row["misses"].append(f"{s['id']} {check}: got intent={p['intent']} amount={p['amount_rupees']} "
                                     f"customer={p['customer_name']} qty={p['quantity']}")
    return summary


TOOLS = [
    {"type": "function", "function": {
        "name": "balances", "description": "List every customer who owes the shop money, and any advances.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "customer_balance", "description": "How much one named customer owes the shop.",
        "parameters": {"type": "object", "properties": {"customer_name": {"type": "string"}},
                       "required": ["customer_name"], "additionalProperties": False}}},
]
TOOL_CASES = [("ఎవరెవరు డబ్బులు ఇవ్వాలి?", "balances", None),
              ("లక్ష్మి ఎంత ఇవ్వాలి?", "customer_balance", "లక్ష్మి"),
              ("ఈ రోజు వాతావరణం ఎలా ఉంది?", None, None)]


def run_tools() -> list[dict]:
    rows = []
    for question, want_tool, want_name in TOOL_CASES:
        start = time.perf_counter()
        r = client.chat.completions.create(
            model=MODEL, max_tokens=4000, tools=TOOLS, tool_choice="auto", parallel_tool_calls=False,
            messages=[{"role": "system", "content": "You are Lekkalu, a bookkeeping assistant for a saree shop. "
                       "Use a tool when the question is about the shop's money; otherwise answer briefly."},
                      {"role": "user", "content": question}])
        msg = r.choices[0].message
        call = msg.tool_calls[0] if msg.tool_calls else None
        args = json.loads(call.function.arguments) if call else None
        got_tool = call.function.name if call else None
        ok = got_tool == want_tool and (want_name is None or name_ok(args.get("customer_name"), want_name))
        rows.append({"question": question, "tool": got_tool, "args": args, "ok": ok,
                     "text": None if call else msg.content, "latency_s": round(time.perf_counter() - start, 2)})
    (OUT / "tools.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = run_extraction()
    print(f"\nstrict json_schema accepted: {strict}\n")
    print(f"{'config':24} {'ok/n':>6} {'intent':>7} {'amount':>7} {'cust':>6} {'qty':>6} {'p50 s':>6} {'reason tok':>10}")
    for key, row in summary.items():
        c = row["checks"]
        cell = lambda k: f"{c[k][0]}/{c[k][1]}" if k in c else "-"  # noqa: E731
        p50 = statistics.median(row["latency"]) if row["latency"] else 0
        rt = round(statistics.mean(row["reasoning"])) if row["reasoning"] else "-"
        print(f"{key:24} {row['n'] - row['failures']:>2}/{row['n']:<3} {cell('intent'):>7} {cell('amount'):>7} "
              f"{cell('customer'):>6} {cell('quantity'):>6} {p50:>6.1f} {rt:>10}")
    for key, row in summary.items():
        for m in row["misses"]:
            print(f"  miss [{key}] {m}")
    (OUT / "summary.json").write_text(json.dumps({"strict": strict, "summary": summary}, ensure_ascii=False, indent=2))

    print("\nTool choice:")
    for t in run_tools():
        print(f"  {'OK ' if t['ok'] else 'BAD'} [{t['latency_s']}s] {t['question']} -> {t['tool']} {t['args'] or ''} "
              f"{(t['text'] or '')[:80]}")


if __name__ == "__main__":
    main()
