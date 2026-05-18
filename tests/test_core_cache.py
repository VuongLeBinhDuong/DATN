"""Tests for core/cache.py - SimpleCache module.

Verifies thread-safe cache operations, LRU eviction, and TTL expiration.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from core.cache import SimpleCache


class TestSimpleCache:
    """Test cases for the in-memory SimpleCache."""

    def test_cache_set_and_get(self):
        """Test setting and retrieving key-value pairs."""
        cache = SimpleCache(default_ttl_sec=60)
        cache.set("key1", "value1")
        
        assert cache.get("key1") == "value1"
        assert cache.get("non_existent") is None

    def test_cache_ttl_expiration(self):
        """Test that values expire after their TTL."""
        cache = SimpleCache(default_ttl_sec=60)
        
        # Immediate expiration using negative TTL
        cache.set("key1", "value1", ttl_sec=-1)
        assert cache.get("key1") is None
        
        # Controlled expiration using mocked time
        with patch("time.time", return_value=1000.0) as mock_time:
            cache.set("key2", "value2", ttl_sec=30)
            
            # Retrieve within TTL
            mock_time.return_value = 1010.0
            assert cache.get("key2") == "value2"
            
            # Retrieve after TTL
            mock_time.return_value = 1040.0
            assert cache.get("key2") is None

    def test_cache_max_size_eviction(self):
        """Test that oldest entries are evicted when max size is exceeded."""
        # Setup cache with max size 3 and default TTL
        cache = SimpleCache(default_ttl_sec=100, max_size=3)
        
        with patch("time.time") as mock_time:
            # Set items with ascending expiry times
            mock_time.return_value = 1000.0
            cache.set("k1", "v1")  # Expiry 1100
            
            mock_time.return_value = 1001.0
            cache.set("k2", "v2")  # Expiry 1101
            
            mock_time.return_value = 1002.0
            cache.set("k3", "v3")  # Expiry 1102
            
            assert len(cache._cache) == 3
            
            # Adding 4th item triggers eviction of the item with oldest expiry ("k1")
            mock_time.return_value = 1003.0
            cache.set("k4", "v4")  # Expiry 1103
            
            assert len(cache._cache) == 3
            assert cache.get("k1") is None
            assert cache.get("k2") == "v2"
            assert cache.get("k3") == "v3"
            assert cache.get("k4") == "v4"

    def test_get_or_compute(self):
        """Test get_or_compute computes once and caches."""
        cache = SimpleCache(default_ttl_sec=100)
        
        mock_fn = MagicMock(return_value="computed_value")
        mock_fn.__name__ = "mock_fn"
        
        # First call - cache miss, should compute
        res1 = cache.get_or_compute(mock_fn, "arg1", kw="kw1")
        assert res1 == "computed_value"
        mock_fn.assert_called_once_with("arg1", kw="kw1")
        
        # Second call - cache hit, should return cached value without computing again
        mock_fn.reset_mock()
        res2 = cache.get_or_compute(mock_fn, "arg1", kw="kw1")
        assert res2 == "computed_value"
        mock_fn.assert_not_called()

    def test_cache_invalidation_by_pattern(self):
        """Test invalidating specific cache entries by pattern."""
        cache = SimpleCache()
        cache.set("k1", "value1")
        cache.set("prefix_k2", "value2")
        
        count = cache.invalidate(pattern="prefix")
        assert count == 1
        assert cache.get("k1") == "value1"
        assert cache.get("prefix_k2") is None

    def test_cache_invalidate_all(self):
        """Test clearing the entire cache."""
        cache = SimpleCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        
        count = cache.invalidate()
        assert count == 2
        assert cache.get("k1") is None
        assert cache.get("k2") is None
        assert len(cache._cache) == 0

    def test_cache_stats(self):
        """Test retrieval of hit/miss statistics."""
        cache = SimpleCache()
        cache.set("k1", "v1")
        
        # 2 hits, 1 miss
        cache.get("k1")
        cache.get("k1")
        cache.get("non_existent")
        
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
