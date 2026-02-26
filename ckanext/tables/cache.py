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

import pandas as pd

from ckan.lib.redis import connect_to_redis

from ckanext.tables.config import get_cache_dir

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
        if isinstance(value, pd.DataFrame):
            value = value.to_dict(orient="records")

        with connect_to_redis() as conn:
            conn.setex(self._full_key(key), ttl, json.dumps(value, cls=_TablesJSONEncoder))

    def delete(self, key: str) -> None:
        with connect_to_redis() as conn:
            conn.delete(self._full_key(key))  # type: ignore


class _FileCacheBackend(CacheBackend, ABC):
    """Base class for file-based cache backends.

    Subclasses only need to define:

    - ``_file_extension`` — e.g. ``".parquet"``
    - ``_read_data(path)`` — deserialise data from the cache file
    - ``_write_data(value, path)`` — serialise data to the cache file

    TTL and non-tabular scalar values are stored in a ``.meta`` JSON sidecar.

    Args:
        cache_dir: Directory where cache files are stored.
    """

    _file_extension: str

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir = cache_dir or get_cache_dir()

    @abstractmethod
    def _read_data(self, path: str) -> Any: ...

    @abstractmethod
    def _write_data(self, value: Any, path: str) -> None: ...

    def _cache_path(self, key: str) -> str:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}{self._file_extension}")

    def _meta_path(self, key: str) -> str:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.meta")

    def get(self, key: str) -> Any:
        meta_path = self._meta_path(key)
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        if time.time() - os.path.getmtime(meta_path) >= meta.get("ttl", 0):
            return None

        if "scalar_value" in meta:
            return meta["scalar_value"]

        path = self._cache_path(key)
        if not os.path.exists(path):
            return None

        try:
            return self._read_data(path)
        except (OSError, ValueError):
            log.debug("Failed to read %s cache %s", self._file_extension, path, exc_info=True)
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        path = self._cache_path(key)
        meta_path = self._meta_path(key)

        try:
            os.makedirs(self.cache_dir, exist_ok=True)

            if isinstance(value, (list, pd.DataFrame)):
                self._write_data(value, path)
                with open(meta_path, "w") as f:
                    json.dump({"ttl": ttl}, f)
            else:
                with open(meta_path, "w") as f:
                    json.dump({"ttl": ttl, "scalar_value": value}, f)
                with contextlib.suppress(FileNotFoundError):
                    os.remove(path)
        except (OSError, ValueError):
            log.warning("Failed to write %s cache %s", self._file_extension, path, exc_info=True)

    def delete(self, key: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            os.remove(self._cache_path(key))
        with contextlib.suppress(FileNotFoundError):
            os.remove(self._meta_path(key))

    def get_cache_path(self, key: str) -> str:
        """Public accessor for the cache file path (useful in tests)."""
        return self._cache_path(key)


class _DataFrameFileCacheBackend(_FileCacheBackend, ABC):
    """File cache backend that serialises values via a pandas DataFrame.

    Subclasses define ``_read_df`` / ``_write_df`` for the actual I/O.
    """

    @abstractmethod
    def _read_df(self, path: str) -> pd.DataFrame: ...

    @abstractmethod
    def _write_df(self, df: pd.DataFrame, path: str) -> None: ...

    def _read_data(self, path: str) -> Any:
        return self._read_df(path)

    def _write_data(self, value: Any, path: str) -> None:
        self._write_df(pd.DataFrame(value), path)


class PickleCacheBackend(_FileCacheBackend):
    """Cache backend that stores data as pickle files on disk."""

    _file_extension = ".pkl"

    def _read_data(self, path: str) -> Any:
        try:
            with open(path, "rb") as f:
                return pickle.load(f)  # noqa: S301
        except pickle.PickleError as err:
            raise ValueError(str(err)) from err

    def _write_data(self, value: Any, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(value, f)


class ParquetCacheBackend(_DataFrameFileCacheBackend):
    """Cache backend that stores data as parquet files on disk."""

    _file_extension = ".parquet"

    def _read_df(self, path: str) -> pd.DataFrame:
        return pd.read_parquet(path)

    def _write_df(self, df: pd.DataFrame, path: str) -> None:
        df.to_parquet(path, engine="pyarrow")


class FeatherCacheBackend(_DataFrameFileCacheBackend):
    """Cache backend that stores data as feather (Arrow IPC) files on disk."""

    _file_extension = ".feather"

    def _read_df(self, path: str) -> pd.DataFrame:
        return pd.read_feather(path)

    def _write_df(self, df: pd.DataFrame, path: str) -> None:
        df.to_feather(path)


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

            def get_cache_key(self) -> str:
                ...

    Example — use parquet files::

        class BaseResourceDataSource(CachedDataSourceMixin, PandasDataSource):
            cache_backend = ParquetCacheBackend("/var/cache/tables")

            def get_cache_key(self) -> str:
                ...

    Example — use feather files::

        class BaseResourceDataSource(CachedDataSourceMixin, PandasDataSource):
            cache_backend = FeatherCacheBackend("/var/cache/tables")

            def get_cache_key(self) -> str:
                ...

    Example — no caching (just don't mix in this class at all)::

        class BaseResourceDataSource(DatabaseDataSource):
            ...
    """

    def get_cache_key(self) -> str:
        """Return a unique string key for this data source instance."""
        raise NotImplementedError
