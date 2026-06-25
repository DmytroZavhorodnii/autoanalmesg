"""
Thread-safe admin feedback store.
Corrections are injected as few-shot examples into future AI prompts,
implementing a lightweight RLHF-style in-context learning loop.
"""

import json
import re
import threading
from pathlib import Path

from app.config import FEEDBACK_FILE, MAX_EXAMPLES


class FeedbackStore:
    def __init__(self):
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        p = Path(FEEDBACK_FILE)
        if not p.exists():
            return
        try:
            with p.open("r", encoding="utf-8") as f:
                self._entries = json.load(f)
        except Exception:
            self._entries = []

    def _save(self):
        with Path(FEEDBACK_FILE).open("w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2, default=str)

    def add(self, msg_id: int, text: str, original: dict, corrected: dict):
        """Record an admin correction."""
        entry = {
            "id":        msg_id,
            "snippet":   text[:300],
            "original":  {k: original.get(k) for k in ("typ", "priorytet", "serwis", "akcja")},
            "corrected": {k: corrected.get(k) for k in ("typ", "priorytet", "serwis", "akcja")},
        }
        with self._lock:
            self._entries = [e for e in self._entries if e["id"] != msg_id]
            self._entries.append(entry)
            self._save()

    def get_examples(self, text: str, n: int = MAX_EXAMPLES) -> list[dict]:
        """Return n most relevant corrections as few-shot examples (bag-of-words similarity)."""
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return []
        query_words = set(w.lower() for w in re.findall(r"\b\w{4,}\b", text))
        scored = []
        for e in entries:
            e_words = set(w.lower() for w in re.findall(r"\b\w{4,}\b", e["snippet"]))
            score = len(query_words & e_words)
            scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        return [e for score, e in scored[:n] if score > 0]

    def list_all(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def delete(self, msg_id: int) -> bool:
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e["id"] != msg_id]
            if len(self._entries) < before:
                self._save()
                return True
        return False
