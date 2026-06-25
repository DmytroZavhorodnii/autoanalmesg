"""
Checkpoint management — saves completed IDs so interrupted runs can resume.
Thread-safe: multiple workers write concurrently via a lock.
"""

import json
import threading
from pathlib import Path

from app.config import CHECKPOINT_FILE

_lock = threading.Lock()


def load() -> dict[int, dict]:
    """Load results from a previous (possibly interrupted) run."""
    p = Path(CHECKPOINT_FILE)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}
    except Exception:
        return {}


def save(msg_id: int, result: dict):
    """Append a single result to the checkpoint file (thread-safe)."""
    p = Path(CHECKPOINT_FILE)
    with _lock:
        existing: dict = {}
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing[str(msg_id)] = result
        with p.open("w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, default=str)


def clear():
    """Delete the checkpoint file."""
    p = Path(CHECKPOINT_FILE)
    with _lock:
        if p.exists():
            p.unlink()
