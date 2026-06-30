"""Lightweight caching utilities for expensive, repeatable computations.

Provides a thread-safe in-memory TTL cache and a decorator. Used to avoid
recomputing deterministic results (the solver uses a fixed seed, so identical
inputs yield identical schedules) and to speed up repeated reads.
"""
from __future__ import annotations

import functools
import hashlib
import json
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    """Thread-safe cache with per-entry time-to-live and a max size."""

    def __init__(self, maxsize: int = 128, ttl_seconds: float = 3600):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if now >= expires_at:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._store) >= self.maxsize:
                # Evict the entry closest to expiry (approximate LRU by TTL).
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])
                del self._store[oldest[0]]
            self._store[key] = (now + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"size": len(self._store), "hits": self.hits,
                    "misses": self.misses}


def make_key(*args: Any, **kwargs: Any) -> str:
    """Build a stable cache key from JSON-serializable arguments."""
    try:
        payload = json.dumps([args, kwargs], sort_keys=True, default=str)
    except TypeError:
        payload = repr((args, kwargs))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached(cache: TTLCache) -> Callable:
    """Decorator that memoizes a function's result in the given TTLCache."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__module__}.{func.__qualname__}:{make_key(*args, **kwargs)}"
            hit = cache.get(key)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache  # type: ignore[attr-defined]
        return wrapper

    return decorator
