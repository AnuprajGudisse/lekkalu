# Copyright (c) 2026 Lekkalu
import shutil
import subprocess

import pytest

from app.speech.audio import AudioError, to_wav

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_browser_recording_becomes_wav_with_real_header_sizes(tmp_path):
    src = tmp_path / "note.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                    "-c:a", "libopus", str(src)], check=True)
    wav = to_wav(src)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert int.from_bytes(wav[4:8], "little") == len(wav) - 8  # a piped WAV would say 0xFFFFFFFF
    assert int.from_bytes(wav[22:24], "little") == 1  # mono
    assert int.from_bytes(wav[24:28], "little") == 24000


def test_unreadable_audio_fails_with_ffmpegs_reason(tmp_path):
    src = tmp_path / "note.webm"
    src.write_bytes(b"not audio")
    with pytest.raises(AudioError, match="Invalid data"):
        to_wav(src)
