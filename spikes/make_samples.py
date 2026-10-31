"""Generate synthetic Telugu voice notes with Sarvam TTS, plus their labels.

Usage: uv run --no-project python spikes/make_samples.py
Audio -> var/samples/ (git-ignored). Labels -> eval/samples.json (committed; synthetic data only).
These stand in for Amma's recordings during development; real recordings replace them for reported metrics.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import env  # noqa: E402

env.load()
import os  # noqa: E402

from sarvamai import SarvamAI  # noqa: E402
from sarvamai.play import save  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "var" / "samples"
LABELS = ROOT / "eval" / "samples.json"

# Amounts in rupees; null means the speaker did not say it (must stay unknown).
SAMPLES = [
    ("sale_profit", "ఒక ఎర్ర చీర వెయ్యి రూపాయలకు అమ్మాను, రెండు వందలు లాభం.",
     {"intent": "sale", "amount_rupees": 1000, "profit_rupees": 200, "quantity": 1, "item": "ఎర్ర చీర", "customer": None}),
    ("credit_sale", "లక్ష్మి రెండు చీరలు తీసుకుంది, రెండు వేల ఐదు వందలు, తర్వాత ఇస్తుంది.",
     {"intent": "credit_sale", "amount_rupees": 2500, "quantity": 2, "item": "చీర", "customer": "లక్ష్మి"}),
    ("repayment", "లక్ష్మి వెయ్యి రూపాయలు ఇచ్చింది.",
     {"intent": "payment_received", "amount_rupees": 1000, "customer": "లక్ష్మి"}),
    ("purchase", "హోల్‌సేల్ దగ్గర పది చీరలు కొన్నాను, పదిహేను వేలు అయింది.",
     {"intent": "purchase", "amount_rupees": 15000, "quantity": 10, "item": "చీర", "customer": None}),
    ("expense", "ఆటోకి నూట యాభై రూపాయలు ఖర్చు అయింది.",
     {"intent": "expense", "amount_rupees": 150, "item": "ఆటో", "customer": None}),
    ("credit_codemix", "సుజాత ఒక silk saree తీసుకుంది, three thousand rupees, అప్పు రాసుకో.",
     {"intent": "credit_sale", "amount_rupees": 3000, "quantity": 1, "item": "silk saree", "customer": "సుజాత"}),
    ("sale_paatika", "రెండు కాటన్ చీరలు పాతిక వందలకు అమ్మాను.",
     {"intent": "sale", "amount_rupees": 2500, "quantity": 2, "item": "కాటన్ చీర", "customer": None}),
    ("missing_amount", "పద్మ ఒక చీర తీసుకుంది, డబ్బులు తర్వాత ఇస్తుంది.",
     {"intent": "credit_sale", "amount_rupees": None, "quantity": 1, "item": "చీర", "customer": "పద్మ"}),
    ("correction", "తప్పు, ఇందాక చెప్పింది రెండు వేలు కాదు, పదిహేను వందలు.",
     {"intent": "correction", "amount_rupees": 1500, "customer": None}),
    ("query_owed", "ఎవరెవరు డబ్బులు ఇవ్వాలి?",
     {"intent": "query", "amount_rupees": None, "customer": None}),
]


def main() -> None:
    client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])
    AUDIO.mkdir(parents=True, exist_ok=True)
    labels = []
    for i, (name, text, label) in enumerate(SAMPLES, 1):
        audio = AUDIO / f"{i:02d}_{name}.wav"
        if not audio.exists():
            save(client.text_to_speech.convert(text=text, language_code="te-IN", model="bulbul:v4-flash"), str(audio))
        labels.append({"id": f"{i:02d}_{name}", "source": "synthetic_tts", "audio": f"var/samples/{audio.name}",
                       "reference_text": text, "expected": label})
        print(f"{audio.name}  {text}")
    LABELS.parent.mkdir(exist_ok=True)
    LABELS.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n")
    print(f"\n{len(labels)} samples -> {AUDIO}, labels -> {LABELS}")


if __name__ == "__main__":
    main()
