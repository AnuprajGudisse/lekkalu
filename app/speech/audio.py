# Copyright (c) 2026 Lekkalu
import subprocess
import tempfile
from pathlib import Path


class AudioError(Exception):
    """ffmpeg could not read the recording."""


def to_wav(src: Path) -> bytes:
    """Any browser recording (WebM/Opus, MP4/AAC, Ogg) to the mono 16-bit 24 kHz WAV Muse Voice Transcribe takes.

    Written to a file, not a pipe: piped WAV has no RIFF/data sizes (0xFFFFFFFF), and Muse was only tested
    with real headers.
    """
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "out.wav"
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "24000",
                            "-c:a", "pcm_s16le", "-map_metadata", "-1", str(dst)],
                           check=True, capture_output=True, timeout=30)
        except subprocess.CalledProcessError as e:  # keep ffmpeg's own reason in messages.error
            raise AudioError(f"ffmpeg exit {e.returncode}: {e.stderr.decode(errors='replace').strip()[:500]}") from e
        return dst.read_bytes()
