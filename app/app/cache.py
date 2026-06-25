"""Thread-safe in-memory cache for classification results (keyed by MD5 hash)."""

import hashlib
import threading


class ResultCache:
    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.hits = 0

    def _key(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()

    def get(self, text: str) -> dict | None:
        k = self._key(text)
        with self._lock:
            result = self._store.get(k)
            if result:
                self.hits += 1
            return result

    def set(self, text: str, result: dict):
        with self._lock:
            self._store[self._key(text)] = result

    def clear(self):
        with self._lock:
            self._store.clear()
            self.hits = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)
