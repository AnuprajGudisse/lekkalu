# Copyright (c) 2026 Lekkalu
"""Live check of the app's MetaExtractor (nested `lines` schema). Writes raw content to spikes/out/lines/.

Usage: uv run python spikes/extract_lines.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.providers.meta import MetaExtractor  # noqa: E402
from app.ai.schemas import Extraction  # noqa: E402

CASES = {
    "credit_sale": "లక్ష్మి రెండు చీరలు తీసుకుంది, రెండు వేల ఐదు వందలు, తర్వాత ఇస్తుంది",
    "two_transactions": "రెండు చీరలు అమ్మా, ఆటోకి 150",
    "missing_amount": "పద్మ ఒక చీర తీసుకుంది, డబ్బులు తర్వాత ఇస్తుంది",
    "sale_profit": "ఒక ఎర్ర చీర వెయ్యి రూపాయలకు అమ్మాను, రెండు వందలు లాభం.",
}

out = ROOT / "spikes" / "out" / "lines"
out.mkdir(parents=True, exist_ok=True)
ext = MetaExtractor()
for name, text in CASES.items():
    start = time.perf_counter()
    try:
        content = ext.complete(text)
    except Exception as e:  # report every failure, keep going
        print(f"FAIL {name}: {type(e).__name__}: {str(e)[:300]}")
        continue
    elapsed = round(time.perf_counter() - start, 2)
    (out / f"{name}.json").write_text(json.dumps({"input": text, "content": content}, ensure_ascii=False, indent=2))
    lines = Extraction.model_validate_json(content).lines
    print(f"{name} [{elapsed}s] {len(lines)} line(s)")
    for line in lines:
        print("   ", line.model_dump_json())
