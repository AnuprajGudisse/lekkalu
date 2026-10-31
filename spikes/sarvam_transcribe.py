"""Day 1 Sarvam spike: Telugu transcript + English translation for one audio file.

Usage: uv run --env-file .env spikes/sarvam_transcribe.py [audio_path]
Without a path, a synthetic Telugu sample is generated with TTS first.
"""
import os
import sys
import time
from pathlib import Path

from sarvamai import SarvamAI
from sarvamai.play import save

OUT = Path(__file__).parent / "out"
SAMPLE_TEXT = "లక్ష్మి రెండు చీరలు తీసుకుంది, రెండు వేల ఐదు వందలు, తర్వాత ఇస్తుంది."

client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])

if len(sys.argv) > 1:
    audio_path = Path(sys.argv[1])
else:
    # ponytail: synthetic sample only proves the API works; real voice notes come from Amma.
    OUT.mkdir(exist_ok=True)
    audio_path = OUT / "synthetic_te.wav"
    save(client.text_to_speech.convert(text=SAMPLE_TEXT, language_code="te-IN", model="bulbul:v4-flash"), str(audio_path))
    print(f"generated {audio_path}")

for mode in ("transcribe", "translate"):
    start = time.perf_counter()
    with open(audio_path, "rb") as f:
        r = client.speech_to_text.transcribe(file=f, model="saaras:v4", mode=mode, language_code="te-IN")
    print(f"[{mode}] {time.perf_counter() - start:.1f}s lang={r.language_code}\n  {r.transcript}")
