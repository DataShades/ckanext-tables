from __future__ import annotations

import logging
import os
import tempfile
from typing import TYPE_CHECKING

import ckan.plugins.toolkit as tk

if TYPE_CHECKING:
    from ckanext.tables.cache import CacheBackend

log = logging.getLogger(__name__)

CONF_CACHE_BACKEND = "ckanext.tables.cache.backend"
CONF_CACHE_DIR = "ckanext.tables.cache.cache_dir"
CONF_CACHE_TTL = "ckanext.tables.cache.ttl"
CONF_FETCH_CONNECT_TIMEOUT = "ckanext.tables.fetch.connect_timeout"
CONF_FETCH_READ_TIMEOUT = "ckanext.tables.fetch.read_timeout"
CONF_FETCH_MAX_BYTES = "ckanext.tables.fetch.max_bytes"

DEFAULT_CACHE_BACKEND = "feather"
DEFAULT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "tables-cache")
DEFAULT_CACHE_TTL = 3600
DEFAULT_FETCH_CONNECT_TIMEOUT = 5
DEFAULT_FETCH_READ_TIMEOUT = 30
DEFAULT_FETCH_MAX_BYTES = 200 * 1024 * 1024  # 200 MB


def get_cache_dir() -> str:
    cache_dir = tk.config.get(CONF_CACHE_DIR, DEFAULT_CACHE_DIR)

    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir)
        except OSError:
            cache_dir = tempfile.gettempdir()

    return cache_dir


def get_cache_ttl() -> int:
    """Return the configured cache TTL in seconds.

    Reads ``ckanext.tables.cache.ttl``. Defaults to 3600 (1 hour).
    """
    return tk.config.get(CONF_CACHE_TTL, DEFAULT_CACHE_TTL)


def get_fetch_connect_timeout() -> float:
    """Return the connect timeout (seconds) for remote resource/file_url fetches.

    Reads ``ckanext.tables.fetch.connect_timeout``. Defaults to 5.
    """
    return tk.config.get(CONF_FETCH_CONNECT_TIMEOUT, DEFAULT_FETCH_CONNECT_TIMEOUT)


def get_fetch_read_timeout() -> float:
    """Return the read timeout (seconds) for remote resource/file_url fetches.

    Reads ``ckanext.tables.fetch.read_timeout``. Defaults to 30.
    """
    return tk.config.get(CONF_FETCH_READ_TIMEOUT, DEFAULT_FETCH_READ_TIMEOUT)


def get_fetch_max_bytes() -> int:
    """Return the maximum response size (bytes) allowed for remote fetches.

    Reads ``ckanext.tables.fetch.max_bytes``. Defaults to 200 MB.
    """
    return tk.config.get(CONF_FETCH_MAX_BYTES, DEFAULT_FETCH_MAX_BYTES)


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
    # Deferred import to avoid a circular dependency (cache.py imports config.py).
    from ckanext.tables.shared import (  # noqa: PLC0415
        FeatherCacheBackend,
        ParquetCacheBackend,
        PickleCacheBackend,
        RedisCacheBackend,
    )

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
