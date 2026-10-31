# Copyright (c) 2026 Lekkalu
"""Spike: Muse Voice Transcribe (with and without keywords) vs Sarvam on the labeled samples.

Usage: uv run python spikes/stt_compare.py [--only SAMPLE_ID]
Writes raw responses and spikes/out/stt/transcripts.json (read by spark_extract.py).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import env  # noqa: E402

env.load()

import httpx  # noqa: E402
from sarvamai import SarvamAI  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spikes" / "out" / "stt"
BASE_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1")
STT_MODEL = os.environ.get("META_STT_MODEL", "muse-voice-transcribe-1.0")
KEYWORDS = ["లక్ష్మి", "సుజాత", "పద్మ", "చీర", "కాటన్", "silk saree", "పాతిక"]


def to_wav24k(src: Path) -> Path:
    dst = OUT / f"{src.stem}_24k.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "24000",
                    "-c:a", "pcm_s16le", "-map_metadata", "-1", str(dst)], check=True)
    return dst


def muse(wav: Path, keywords: list[str] | None) -> tuple[dict, float]:
    request = {"mode": "ENDPOINTING", "model": STT_MODEL, "audioEncoding": "WAV",
               "languageBias": ["Telugu", "English"]}
    if keywords:
        request["keywords"] = keywords
    start = time.perf_counter()
    r = httpx.post(f"{BASE_URL}/asr/transcribe",
                   headers={"Authorization": f"Bearer {os.environ['META_API_KEY']}"},
                   files={"request": (None, json.dumps(request, ensure_ascii=False), "application/json"),
                          "audio": (wav.name, wav.read_bytes(), "audio/wav")},
                   timeout=30)
    elapsed = time.perf_counter() - start
    if r.status_code != 200:
        raise SystemExit(f"Muse STT HTTP {r.status_code}: {r.text[:500]}")
    return r.json(), elapsed


def sarvam(client: SarvamAI, audio: Path, mode: str) -> tuple[dict, float]:
    start = time.perf_counter()
    with open(audio, "rb") as f:
        r = client.speech_to_text.transcribe(file=f, model="saaras:v4", mode=mode, language_code="te-IN")
    return r.model_dump(), time.perf_counter() - start


def amount_survived(transcript: str, expected_rupees) -> str:
    if expected_rupees is None:
        return "n/a"
    digits = "".join(c for c in transcript if c.isdigit())
    return "digits" if str(int(expected_rupees)) in digits else "words?"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only")
    args = p.parse_args()

    samples = json.loads((ROOT / "eval" / "samples.json").read_text())
    if args.only:
        samples = [s for s in samples if s["id"] == args.only]
    OUT.mkdir(parents=True, exist_ok=True)
    combined_path = OUT / "transcripts.json"
    combined = json.loads(combined_path.read_text()) if combined_path.exists() else {}
    client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])

    for s in samples:
        audio = ROOT / s["audio"]
        wav = to_wav24k(audio)
        runs = {
            "muse": muse(wav, None),
            "muse_kw": muse(wav, KEYWORDS),
            "sarvam_te": sarvam(client, audio, "transcribe"),
            "sarvam_en": sarvam(client, audio, "translate"),
        }
        row = {"reference": s["reference_text"], "latency_s": {}}
        for name, (raw, secs) in runs.items():
            (OUT / f"{s['id']}_{name}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2))
            row[name] = raw.get("transcript") or ""
            row["latency_s"][name] = round(secs, 2)
        combined[s["id"]] = row
        combined_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2))

        amount = s["expected"].get("amount_rupees")
        print(f"\n{s['id']}  (expected amount: {amount})")
        print(f"  ref        {s['reference_text']}")
        for name in runs:
            print(f"  {name:10} [{row['latency_s'][name]:>4}s] {row[name]}  <{amount_survived(row[name], amount)}>")


if __name__ == "__main__":
    main()
