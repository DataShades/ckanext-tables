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
CONF_CACHE_DIR = "ckanext.tables.cache.pickle.cache_dir"


def get_cache_dir() -> str:
    default_cache = os.path.join(tempfile.gettempdir(), "ckanext-tables-cache")
    cache_dir = tk.config.get(CONF_CACHE_DIR, default_cache)

    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir)
        except OSError:
            cache_dir = tempfile.gettempdir()

    return cache_dir


def get_cache_backend() -> CacheBackend:
    """Return a CacheBackend instance based on the configured backend.

    Reads ``ckanext.tables.cache.backend`` and returns the appropriate
    backend instance.

    Supported values:

    * ``"pickle"`` *(default)* — disk-based pickle cache, path controlled by
      ``ckanext.tables.cache.pickle.cache_dir``.
    * ``"redis"`` — CKAN's Redis connection (requires Redis to be configured).

    Unknown values fall back to ``"pickle"`` with a warning.
    """
    # Deferred import to avoid a circular dependency (cache.py imports config.py).
    from ckanext.tables.shared import PickleCacheBackend, RedisCacheBackend  # noqa: PLC0415

    backend = tk.config.get(CONF_CACHE_BACKEND, "pickle").strip().lower()

    if backend == "redis":
        return RedisCacheBackend()

    if backend != "pickle":
        log.warning(
            "Unknown ckanext.tables.cache.backend value %r — falling back to 'pickle'.",
            backend,
        )

    return PickleCacheBackend()
