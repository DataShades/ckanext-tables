from __future__ import annotations

import contextlib
import decimal
import hashlib
import json
import logging
import os
import pickle
import time
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from ckan.lib.redis import connect_to_redis

log = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract cache backend.

    Implement this interface to provide a custom caching strategy for table
    data sources. The cache stores arbitrary JSON-serialisable values keyed
    by a string.
    """

    @abstractmethod
    def get(self, key: str) -> Any:
        """Return the cached value for *key*, or ``None`` if not found / expired."""
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store *value* under *key* with a time-to-live of *ttl* seconds."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the cached value for *key* (no-op if not present)."""
        ...


# class NoCacheBackend(CacheBackend):
#     """A no-op backend that disables caching entirely."""

#     def get(self, key: str) -> Any:
#         return None

#     def set(self, key: str, value: Any, ttl: int) -> None:
#         pass

#     def delete(self, key: str) -> None:
#         pass


class _TablesJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles types commonly found in pandas DataFrames."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", errors="replace")
        # numpy scalars expose .item() to convert to a Python native type
        if hasattr(o, "item"):
            return o.item()
        return super().default(o)


class RedisCacheBackend(CacheBackend):
    """Cache backend backed by CKAN's Redis connection.

    Values are JSON-serialised before storage so they survive across
    processes and server restarts (as long as Redis persists them).
    """

    _PREFIX = "ckanext:tables:"

    def _full_key(self, key: str) -> str:
        return f"{self._PREFIX}{key}"

    def get(self, key: str) -> Any:
        with connect_to_redis() as conn:
            data: bytes | None = conn.get(self._full_key(key))  # type: ignore

        if not data:
            return None

        return json.loads(data)

    def set(self, key: str, value: Any, ttl: int) -> None:
        with connect_to_redis() as conn:
            conn.setex(self._full_key(key), ttl, json.dumps(value, cls=_TablesJSONEncoder))

    def delete(self, key: str) -> None:
        with connect_to_redis() as conn:
            conn.delete(self._full_key(key))  # type: ignore


class PickleCacheBackend(CacheBackend):
    """Cache backend that stores data as pickle files on disk.

    Each key is hashed to a filename inside *cache_dir*. Expiry is
    implemented by comparing the file's modification time against *ttl*.

    Args:
        cache_dir: Directory where cache files are stored.
    """

    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir

    def _cache_path(self, key: str) -> str:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.pkl")

    def get(self, key: str) -> Any:
        path = self._cache_path(key)

        if not os.path.exists(path):
            return None

        try:
            if time.time() - os.path.getmtime(path) >= self._get_ttl(path):
                return None

            with open(path, "rb") as f:
                data = pickle.load(f)  # noqa: S301

            return data["value"] if isinstance(data, dict) and "value" in data else data
        except (OSError, pickle.PickleError):
            log.debug("Failed to read pickle cache %s", path, exc_info=True)
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        path = self._cache_path(key)

        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            # Store ttl alongside value so get() can check expiry correctly
            with open(path, "wb") as f:
                pickle.dump({"ttl": ttl, "value": value}, f)
        except OSError:
            log.warning("Failed to write pickle cache %s", path, exc_info=True)

    def delete(self, key: str) -> None:
        path = self._cache_path(key)
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)

    def _get_ttl(self, path: str) -> int:
        """Read the TTL that was stored alongside the value."""
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)  # noqa: S301
            return data.get("ttl", 0) if isinstance(data, dict) else 0
        except (OSError, pickle.PickleError, AttributeError):
            return 0

    def get_cache_path(self, key: str) -> str:
        """Public accessor for the cache file path (useful in tests)."""
        return self._cache_path(key)


class CachedDataSourceMixin:
    """Mixin that adds pluggable caching to a data source.

    Mix this into any ``BaseDataSource`` subclass to enable caching.
    Override ``cache_backend`` to swap the storage engine, and
    ``cache_ttl`` to change the expiry time.

    Example — use Redis (default)::

        class BaseResourceDataSource(CachedDataSourceMixin, DatabaseDataSource):
            def get_cache_key(self) -> str:
                ...

    Example — use pickle files::

        class BaseResourceDataSource(CachedDataSourceMixin, PandasDataSource):
            cache_backend = PickleCacheBackend("/var/cache/tables")
            cache_ttl = 600

            def get_cache_key(self) -> str:
                ...

    Example — no caching (just don't mix in this class at all)::

        class BaseResourceDataSource(DatabaseDataSource):
            ...
    """

    def get_cache_key(self) -> str:
        """Return a unique string key for this data source instance."""
        raise NotImplementedError
