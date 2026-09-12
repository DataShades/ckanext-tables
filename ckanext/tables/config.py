from __future__ import annotations

import logging
import os
import stat
import tempfile

import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)

CONF_CACHE_BACKEND = "ckanext.tables.cache.backend"
CONF_CACHE_DIR = "ckanext.tables.cache.cache_dir"
CONF_CACHE_TTL = "ckanext.tables.cache.ttl"
CONF_FETCH_CONNECT_TIMEOUT = "ckanext.tables.fetch.connect_timeout"
CONF_FETCH_READ_TIMEOUT = "ckanext.tables.fetch.read_timeout"
CONF_FETCH_MAX_BYTES = "ckanext.tables.fetch.max_bytes"
CONF_MAX_PAGE_SIZE = "ckanext.tables.pagination.max_page_size"
CONF_EXPORT_MAX_ROWS = "ckanext.tables.export.max_rows"

DEFAULT_CACHE_BACKEND = "feather"
DEFAULT_CACHE_TTL = 3600
DEFAULT_FETCH_CONNECT_TIMEOUT = 5
DEFAULT_FETCH_READ_TIMEOUT = 30
DEFAULT_FETCH_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
DEFAULT_MAX_PAGE_SIZE = 100
DEFAULT_EXPORT_MAX_ROWS = 50_000

# Directory permission bits that must *not* be set for a cache directory to
# be considered private: group- or other-writable.
_UNSAFE_DIR_MODE_BITS = stat.S_IWGRP | stat.S_IWOTH


def _default_cache_dir() -> str:
    """Return the default cache directory."""
    storage_path = tk.config.get("ckan.storage_path")

    if storage_path:
        return os.path.join(storage_path, "tables-cache")

    return os.path.join(tempfile.gettempdir(), "tables-cache")


def _is_private_dir(path: str) -> bool:
    """Return True if *path* is a directory only the current user can write to."""
    try:
        st = os.stat(path)
    except OSError:
        return False

    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & _UNSAFE_DIR_MODE_BITS


def get_cache_dir(cache_dir: str | None = None) -> str | None:
    """Return a cache directory that is private to the current process.

    If *cache_dir* is not given, resolves it from ``ckanext.tables.cache.cache_dir``
    (default: a ``tables-cache`` subdirectory of ``ckan.storage_path``, or of the
    system temp directory if that is not configured).

    The directory is created with mode ``0700`` if it does not exist yet. If it
    already exists but is owned by another user, or is group/world-writable, or
    it cannot be created at all, this returns ``None`` rather than falling back
    to a shared, predictable location such as the bare system temp directory.

    That refusal matters: the file-based cache backends derive a cache file's
    name from a hash of its key (a format documented publicly, e.g.
    ``resource-<id>``) inside this directory, and ``PickleCacheBackend`` calls
    ``pickle.load`` on whatever it finds there. A shared or attacker-owned
    directory would let another local user plant a file at that predictable
    path and get arbitrary code executed as the CKAN process the next time
    that resource is previewed.
    """
    if not cache_dir:
        cache_dir = tk.config.get(CONF_CACHE_DIR)

    if not cache_dir:
        cache_dir = _default_cache_dir()

    if os.path.isdir(cache_dir):
        if _is_private_dir(cache_dir):
            return cache_dir

        log.warning(
            "Cache directory %r exists but is not private to this process (owned by "
            "another user, or group/world writable) — refusing to use it for table "
            "caching. Fix its ownership/permissions, or point %s elsewhere.",
            cache_dir,
            CONF_CACHE_DIR,
        )
        return None

    try:
        os.makedirs(cache_dir, mode=0o700)
        os.chmod(cache_dir, 0o700)  # mode= above is subject to umask; make the result deterministic
    except OSError:
        log.warning("Could not create cache directory %r — table caching is disabled.", cache_dir, exc_info=True)
        return None

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


def get_max_page_size() -> int:
    """Return the maximum number of rows a single AJAX page request may return."""
    return tk.config.get(CONF_MAX_PAGE_SIZE, DEFAULT_MAX_PAGE_SIZE)


def get_export_max_rows() -> int:
    """Return the maximum number of rows a single export may contain."""
    return tk.config.get(CONF_EXPORT_MAX_ROWS, DEFAULT_EXPORT_MAX_ROWS)
