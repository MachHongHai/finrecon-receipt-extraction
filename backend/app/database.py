from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_UPLOAD_DIR = DEFAULT_DATA_DIR / "uploads"

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DEFAULT_UPLOAD_DIR))


def ensure_storage() -> None:
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
