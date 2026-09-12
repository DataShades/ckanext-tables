from __future__ import annotations

import contextlib
import decimal
import glob
import hashlib
import json
import logging
import os
import pickle
import tempfile
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd
import pyarrow as pa

import ckan.plugins.toolkit as tk
from ckan.lib.redis import connect_to_redis

from ckanext.tables.config import CONF_CACHE_BACKEND, DEFAULT_CACHE_BACKEND, get_cache_dir

log = logging.getLogger(__name__)

# Cap on how many distinct cache files a single worker process memoises in RAM
# at once (see _FileCacheBackend._memo) — bounds memory use across many
# distinct cached tables rather than letting the in-process copy grow forever.
_MEMO_MAX_ENTRIES = 32

# How old a leftover _atomic_write ".tmp-*" file must be before clean_expired
# treats it as abandoned (from a crashed write) rather than one still in progress.
_STALE_TMP_FILE_AGE = 3600


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

    def clean_expired(self) -> int:
        """Delete every expired entry, returning how many were removed.

        The default is a no-op: only backends whose entries can otherwise
        outlive their TTL indefinitely (the file-based backends — an entry
        that's never read again after expiring would otherwise sit on disk
        forever) need to override this. Redis already expires and removes
        its own keys via ``SETEX``, so it does not.
        """
        return 0


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

    # Same shape/purpose as _FileCacheBackend._memo: a small, in-process
    # LRU of already-decoded values, keyed by the full Redis key, valid as
    # of a version token. `get` still does one Redis round trip to check
    # that token, but skips fetching and json-decoding the (potentially
    # large) payload itself when it's unchanged.
    _memo: OrderedDict[str, tuple[bytes, Any]] = OrderedDict()
    _memo_lock = threading.Lock()

    def _full_key(self, key: str) -> str:
        return f"{self._PREFIX}{key}"

    def _version_key(self, key: str) -> str:
        return f"{self._PREFIX}{key}:v"

    def get(self, key: str) -> Any:
        full_key = self._full_key(key)

        with connect_to_redis() as conn:
            version: bytes | None = conn.get(self._version_key(key))  # type: ignore

            if version is None:
                self._memo_delete(full_key)
                return None

            with self._memo_lock:
                entry = self._memo.get(full_key)
                if entry is not None and entry[0] == version:
                    self._memo.move_to_end(full_key)
                    return entry[1]

            data: bytes | None = conn.get(full_key)  # type: ignore

        if not data:
            return None

        value = json.loads(data)
        self._memo_set(full_key, version, value)
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        if isinstance(value, pd.DataFrame):
            value = value.to_dict(orient="records")

        with connect_to_redis() as conn:
            conn.setex(self._full_key(key), ttl, json.dumps(value, cls=_TablesJSONEncoder))
            conn.setex(self._version_key(key), ttl, uuid.uuid4().hex)

    def delete(self, key: str) -> None:
        with connect_to_redis() as conn:
            conn.delete(self._full_key(key))
            conn.delete(self._version_key(key))

        self._memo_delete(self._full_key(key))

    def _memo_set(self, full_key: str, version: bytes, value: Any) -> None:
        with self._memo_lock:
            self._memo[full_key] = (version, value)
            self._memo.move_to_end(full_key)

            while len(self._memo) > _MEMO_MAX_ENTRIES:
                self._memo.popitem(last=False)

    def _memo_delete(self, full_key: str) -> None:
        with self._memo_lock:
            self._memo.pop(full_key, None)


class _FileCacheBackend(CacheBackend, ABC):
    """Base class for file-based cache backends.

    Subclasses only need to define:

    - ``_file_extension`` — e.g. ``".parquet"``
    - ``_read_data(path)`` — deserialise data from the cache file
    - ``_write_data(value, path)`` — serialise data to the cache file

    TTL and non-tabular scalar values are stored in a ``.meta`` JSON sidecar.

    Args:
        cache_dir: Directory where cache files are stored. Validated (and
            created with mode ``0700`` if missing) the same way as the
            configured/default directory — see :func:`ckanext.tables.config.get_cache_dir`.
            If it cannot be made private to this process, caching is
            silently disabled (every ``get``/``set``/``delete`` becomes a
            no-op) rather than writing to a shared, predictable location.
    """

    _file_extension: str

    # Shared across every instance of every subclass within this process —
    # deliberately a class attribute rather than set in __init__, since a fresh
    # backend instance is constructed per request (see get_cache_backend() below),
    # and the whole point is for the memo to outlive any single instance. Keyed by
    # the resolved cache file path (already unique per directory/key/extension) to
    # a (meta file mtime, deserialised value) pair; a request that re-reads the
    # same still-fresh cache file within the same worker process is served from
    # RAM instead of re-reading and re-deserialising the file from disk.
    _memo: OrderedDict[str, tuple[float, Any]] = OrderedDict()
    _memo_lock = threading.Lock()

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir: str | None = get_cache_dir(cache_dir)

    @abstractmethod
    def _read_data(self, path: str) -> Any: ...

    @abstractmethod
    def _write_data(self, value: Any, path: str) -> None: ...

    def _memo_get(self, path: str, mtime: float) -> tuple[bool, Any]:
        """Return ``(True, value)`` if *path* has a memoised copy as of *mtime*."""
        with self._memo_lock:
            entry = self._memo.get(path)
            if entry is not None and entry[0] == mtime:
                self._memo.move_to_end(path)
                return True, entry[1]

        return False, None

    def _memo_set(self, path: str, mtime: float, value: Any) -> None:
        with self._memo_lock:
            self._memo[path] = (mtime, value)
            self._memo.move_to_end(path)

            while len(self._memo) > _MEMO_MAX_ENTRIES:
                self._memo.popitem(last=False)

    def _memo_delete(self, path: str) -> None:
        with self._memo_lock:
            self._memo.pop(path, None)

    def _require_cache_dir(self) -> str:
        """Return ``self.cache_dir``, which callers must have already checked is not ``None``.

        ``_cache_path``/``_meta_path`` are only ever reached from ``get``/``set``/``delete``,
        each of which returns early when ``self.cache_dir is None`` — this just gives that
        already-established invariant a return type a type checker can rely on, and raises
        instead of silently joining with ``None`` if that invariant is ever violated.
        """
        if self.cache_dir is None:
            raise RuntimeError("Cache directory is not available")

        return self.cache_dir

    def _cache_path(self, key: str) -> str:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self._require_cache_dir(), f"{key_hash}{self._file_extension}")

    def _meta_path(self, key: str) -> str:
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self._require_cache_dir(), f"{key_hash}.meta")

    def _atomic_write(self, final_path: str, writer: Callable[[str], None]) -> None:
        """Write via a same-directory temp file, then atomically replace *final_path*.

        A concurrent ``get`` opens ``final_path`` directly, never the temp file, so it can
        only ever see the previous complete version or the new complete version — never a
        half-written one (``os.replace`` is atomic on POSIX within the same filesystem).
        """
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(final_path), prefix=".tmp-")
        os.close(fd)
        try:
            writer(tmp_path)
            os.replace(tmp_path, final_path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp_path)
            raise

    def get(self, key: str) -> Any:  # noqa: PLR0911
        if self.cache_dir is None:
            return None

        meta_path = self._meta_path(key)
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        expires_at = meta.get("expires_at")
        if expires_at is None or time.time() >= expires_at:
            # An entry that's never read again after expiring would otherwise sit
            # on disk forever (see clean_expired for entries that never get here).
            # A missing expires_at (an entry from before this field existed, or a
            # corrupted write) is likewise treated as expired rather than trusted.
            self.delete(key)
            return None

        if "scalar_value" in meta:
            return meta["scalar_value"]

        path = self._cache_path(key)

        hit, value = self._memo_get(path, expires_at)
        if hit:
            return value

        if not os.path.exists(path):
            return None

        try:
            value = self._read_data(path)
        except (OSError, ValueError):
            log.debug("Failed to read %s cache %s", self._file_extension, path, exc_info=True)
            return None

        self._memo_set(path, expires_at, value)
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        if self.cache_dir is None:
            return

        path = self._cache_path(key)
        meta_path = self._meta_path(key)
        expires_at = time.time() + ttl

        try:
            if isinstance(value, (list, pd.DataFrame)):
                # Write the data file first and only then commit the meta file that
                # points to it, so a reader that observes the new meta always finds a
                # complete, matching data file — never a stale or half-written one.
                self._atomic_write(path, lambda tmp: self._write_data(value, tmp))
                self._atomic_write(meta_path, lambda tmp: self._write_meta(tmp, {"expires_at": expires_at}))
            else:
                self._atomic_write(
                    meta_path, lambda tmp: self._write_meta(tmp, {"expires_at": expires_at, "scalar_value": value})
                )
                with contextlib.suppress(FileNotFoundError):
                    os.remove(path)
        except (OSError, ValueError, TypeError, pa.ArrowException):
            # ArrowTypeError (mixed-type object columns, e.g. from XLSX/CSV) is a
            # TypeError, not a ValueError, so it needs its own catch.
            log.warning("Failed to write %s cache %s", self._file_extension, path, exc_info=True)

    def _write_meta(self, path: str, meta: dict[str, Any]) -> None:
        with open(path, "w") as f:
            json.dump(meta, f)

    def delete(self, key: str) -> None:
        if self.cache_dir is None:
            return

        self._memo_delete(self._cache_path(key))

        with contextlib.suppress(FileNotFoundError):
            os.remove(self._cache_path(key))
        with contextlib.suppress(FileNotFoundError):
            os.remove(self._meta_path(key))

    def get_cache_path(self, key: str) -> str:
        """Public accessor for the cache file path (useful in tests)."""
        return self._cache_path(key)

    def clean_expired(self) -> int:  # noqa: C901
        """Delete every expired cache entry in this directory, of any format.

        ``get`` already deletes an entry the next time it's read past its TTL,
        but a key that's never read again — a resource that's since been
        removed or renamed, or a one-off filter/page/sort count key — would
        otherwise leave its file on disk forever; this sweeps the whole
        directory for that case. Intended to be run periodically (e.g. from a
        cron-triggered CLI command), not on every request.

        Sweeps every ``.meta`` sidecar regardless of which backend wrote its
        matching data file (they all share the same sidecar format), so this
        also cleans up entries left behind by a since-changed
        ``ckanext.tables.cache.backend`` setting. Returns how many entries
        were removed.
        """
        if self.cache_dir is None:
            return 0

        try:
            entries = list(os.scandir(self.cache_dir))
        except OSError:
            return 0

        removed = 0
        now = time.time()

        for entry in entries:
            # A ".tmp-*" file only exists if a write via _atomic_write crashed between
            # creating it and the os.replace that would have consumed it — sweep it
            # once it's old enough that it can't be a write still in progress.
            if entry.name.startswith(".tmp-"):
                with contextlib.suppress(OSError):
                    if now - entry.stat().st_mtime >= _STALE_TMP_FILE_AGE:
                        os.remove(entry.path)
                        removed += 1
                continue

            if not entry.name.endswith(".meta"):
                continue

            try:
                with open(entry.path) as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            expires_at = meta.get("expires_at")
            if expires_at is not None and now < expires_at:
                continue

            key_hash = entry.name[: -len(".meta")]

            for data_path in glob.glob(os.path.join(self.cache_dir, f"{key_hash}.*")):
                if data_path == entry.path:
                    continue

                with contextlib.suppress(FileNotFoundError):
                    os.remove(data_path)

                self._memo_delete(data_path)

            with contextlib.suppress(FileNotFoundError):
                os.remove(entry.path)

            removed += 1

        return removed


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


def get_cache_backend() -> CacheBackend:
    """Return a CacheBackend instance based on the configured backend.

    Reads ``ckanext.tables.cache.backend`` and returns the appropriate
    backend instance.

    Supported values:

    * ``"pickle"`` — disk-based pickle cache, path controlled by
      ``ckanext.tables.cache.cache_dir``.
    * ``"redis"`` — CKAN's Redis connection (requires Redis to be configured).
    * ``"parquet"`` — disk-based parquet cache, path controlled by
      ``ckanext.tables.cache.cache_dir``.
    * ``"feather"``  *(default)* — disk-based feather (Arrow IPC) cache, path controlled by
      ``ckanext.tables.cache.cache_dir``.

    Unknown values fall back to ``"feather"`` with a warning.
    """
    backend = tk.config.get(CONF_CACHE_BACKEND, DEFAULT_CACHE_BACKEND).strip().lower()

    if backend == "redis":
        return RedisCacheBackend()

    if backend == "parquet":
        return ParquetCacheBackend()

    if backend == "pickle":
        return PickleCacheBackend()

    if backend != DEFAULT_CACHE_BACKEND:
        log.warning(
            "Unknown %s value %r — falling back to %r.",
            CONF_CACHE_BACKEND,
            backend,
            DEFAULT_CACHE_BACKEND,
        )

    return FeatherCacheBackend()


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

    cache_backend: CacheBackend
    cache_ttl: int

    def get_cache_key(self) -> str:
        """Return a unique string key for this data source instance."""
        raise NotImplementedError

    def invalidate(self) -> None:
        """Remove this data source's cached DataFrame and orphan every count derived from it."""
        invalidate_cache_entry(self.cache_backend, self.get_cache_key(), self.cache_ttl)


def invalidate_cache_entry(cache_backend: CacheBackend, key: str, ttl: int) -> None:
    """Delete *key* and make every count cached against it unreachable.

    A count is cached per distinct filter combination a user has applied (see
    ``TableDefinition._count_cache_key``) — an unbounded set that can't be
    enumerated and deleted directly. Bumping a generation token stored under
    ``f"{key}:gen"`` instead means any count computed *after* this call uses a
    new key, so a stale one is never served again; the orphaned old entries
    are simply left to expire via their own TTL, like any other expired entry.
    """
    cache_backend.delete(key)
    cache_backend.set(f"{key}:gen", uuid.uuid4().hex, ttl)
