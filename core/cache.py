"""Simple in-memory cache for query results.

Provides TTL-based caching for expensive operations like GraphRAG queries.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SimpleCache:
    """In-memory cache with TTL support."""

    def __init__(self, default_ttl_sec: int = 300, max_size: int = 1000) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl_sec
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Create cache key from arguments."""
        key_data = repr((args, sorted(kwargs.items())))
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        if key not in self._cache:
            self._misses += 1
            return None

        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl_sec: int | None = None) -> None:
        """Cache value with TTL."""
        # Evict oldest if at capacity (simple LRU)
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]

        ttl = ttl_sec or self._default_ttl
        self._cache[key] = (value, time.time() + ttl)

    def get_or_compute(
        self,
        compute_fn: Any,
        *args: Any,
        ttl_sec: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Get from cache or compute and cache."""
        key = self._make_key(compute_fn.__name__, *args, **kwargs)

        cached = self.get(key)
        if cached is not None:
            logger.debug("Cache hit for %s", compute_fn.__name__)
            return cached

        logger.debug("Cache miss for %s", compute_fn.__name__)
        result = compute_fn(*args, **kwargs)
        self.set(key, result, ttl_sec)
        return result

    def invalidate(self, pattern: str | None = None) -> int:
        """Invalidate cache entries matching pattern."""
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        to_remove = [k for k in self._cache if pattern in k]
        for k in to_remove:
            del self._cache[k]
        return len(to_remove)

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
            "max_size": self._max_size,
            "default_ttl": self._default_ttl,
        }


# Global cache instance
_query_cache: SimpleCache | None = None


def get_query_cache() -> SimpleCache:
    """Get or create global query cache."""
    global _query_cache
    if _query_cache is None:
        _query_cache = SimpleCache(default_ttl_sec=300, max_size=500)
    return _query_cache


def clear_query_cache() -> None:
    """Clear global query cache."""
    global _query_cache
    if _query_cache is not None:
        _query_cache.invalidate()
