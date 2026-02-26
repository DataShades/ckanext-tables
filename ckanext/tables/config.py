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

DEFAULT_CACHE_TTL = 3600


def get_cache_dir() -> str:
    default_cache = os.path.join(tempfile.gettempdir(), "ckanext-tables-cache")
    cache_dir = tk.config.get(CONF_CACHE_DIR, default_cache)

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

    backend = tk.config.get(CONF_CACHE_BACKEND, "pickle").strip().lower()

    if backend == "redis":
        return RedisCacheBackend()

    if backend == "parquet":
        return ParquetCacheBackend()

    if backend == "pickle":
        return PickleCacheBackend()

    if backend != "feather":
        log.warning(
            "Unknown ckanext.tables.cache.backend value %r — falling back to 'feather'.",
            backend,
        )

    return FeatherCacheBackend()
