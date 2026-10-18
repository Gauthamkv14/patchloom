"""Size-bounded, TTL-aware in-memory cache."""

import time
from typing import Any, Optional


class CacheEntry:
    """Single cached entry with expiry time."""

    def __init__(self, value: Any, ttl_seconds: float):
        self.value = value
        self.expires_at = time.monotonic() + ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class InMemoryCache:
    """Thread-safe, size-bounded in-memory LRU-like cache."""

    def __init__(self, max_entries: int = 200):
        self._max_entries = max_entries
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        """Retrieve entry if present and not expired."""
        entry = self._store.get(key)
        if not entry:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float = 120.0) -> None:
        """Store entry with TTL, evicting expired or oldest items if exceeding capacity."""
        # Evict expired entries first
        now = time.monotonic()
        expired_keys = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in expired_keys:
            del self._store[k]

        # If still at capacity, evict the first key (FIFO approximation)
        if len(self._store) >= self._max_entries:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]

        self._store[key] = CacheEntry(value, ttl_seconds)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# Global application cache
app_cache = InMemoryCache(max_entries=200)
