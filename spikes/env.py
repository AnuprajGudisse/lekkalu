# Copyright (c) 2026 Lekkalu
"""Load the project's env file into os.environ for spike scripts (no python-dotenv needed)."""
import os
from pathlib import Path


def load() -> None:
    path = Path(__file__).resolve().parent.parent / ".env"
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())
