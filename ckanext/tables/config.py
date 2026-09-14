from __future__ import annotations

import logging
import os
import stat
import tempfile

import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)

CONF_CACHE_DIR = "ckanext.tables.cache.cache_dir"
CONF_CACHE_TTL = "ckanext.tables.cache.ttl"
CONF_FETCH_CONNECT_TIMEOUT = "ckanext.tables.fetch.connect_timeout"
CONF_FETCH_READ_TIMEOUT = "ckanext.tables.fetch.read_timeout"
CONF_FETCH_MAX_BYTES = "ckanext.tables.fetch.max_bytes"
CONF_MAX_PAGE_SIZE = "ckanext.tables.pagination.max_page_size"
CONF_EXPORT_MAX_ROWS = "ckanext.tables.export.max_rows"
CONF_EXPORT_DIR = "ckanext.tables.export.export_dir"
CONF_EXPORT_JOB_TTL = "ckanext.tables.export.job_ttl"

DEFAULT_CACHE_TTL = 3600
DEFAULT_FETCH_CONNECT_TIMEOUT = 5
DEFAULT_FETCH_READ_TIMEOUT = 30
DEFAULT_FETCH_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
DEFAULT_MAX_PAGE_SIZE = 100
DEFAULT_EXPORT_MAX_ROWS = 50_000
DEFAULT_EXPORT_JOB_TTL = 3600

# Directory permission bits that must *not* be set for a cache directory to
# be considered private: group- or other-writable.
_UNSAFE_DIR_MODE_BITS = stat.S_IWGRP | stat.S_IWOTH


def _default_cache_dir() -> str:
    """Return the default cache directory."""
    storage_path = tk.config.get("ckan.storage_path")

    if storage_path:
        return os.path.join(storage_path, "tables-cache")

    return os.path.join(tempfile.gettempdir(), "tables-cache")


def _default_export_dir() -> str:
    """Return the default background-export output directory.

    A sibling of the cache dir, not a subdirectory of it — the two hold
    different things (resource data vs. rendered export files) keyed by
    different id schemes, so keeping them apart avoids a filename collision
    between an export job id and a resource/url cache key ever mattering.
    """
    storage_path = tk.config.get("ckan.storage_path")

    if storage_path:
        return os.path.join(storage_path, "tables-exports")

    return os.path.join(tempfile.gettempdir(), "tables-exports")


def _is_private_dir(path: str) -> bool:
    """Return True if *path* is a directory only the current user can write to."""
    try:
        st = os.stat(path)
    except OSError:
        return False

    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & _UNSAFE_DIR_MODE_BITS


def _get_private_dir(configured_dir: str | None, default_dir: str, config_key: str, purpose: str) -> str | None:
    """Return a directory that is private to the current process, creating it if needed."""
    directory = configured_dir or default_dir

    if os.path.isdir(directory):
        if _is_private_dir(directory):
            return directory

        log.warning(
            "%s directory %r exists but is not private to this process (owned by "
            "another user, or group/world writable) — refusing to use it. Fix its "
            "ownership/permissions, or point %s elsewhere.",
            purpose,
            directory,
            config_key,
        )
        return None

    try:
        os.makedirs(directory, mode=0o700)
        os.chmod(directory, 0o700)  # mode= above is subject to umask; make the result deterministic
    except OSError:
        log.warning("Could not create %s directory %r — this feature is disabled.", purpose, directory, exc_info=True)
        return None

    return directory


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
    ``resource-<id>``) inside this directory, and read back whatever they
    find there as trusted cache data. A shared or attacker-owned directory
    would let another local user plant a file at that predictable path and
    have it served back as this resource's data the next time it is
    previewed.
    """
    return _get_private_dir(cache_dir or tk.config.get(CONF_CACHE_DIR), _default_cache_dir(), CONF_CACHE_DIR, "Cache")


def get_export_dir(export_dir: str | None = None) -> str | None:
    """Return the background-export output directory, private to the current process."""
    return _get_private_dir(
        export_dir or tk.config.get(CONF_EXPORT_DIR), _default_export_dir(), CONF_EXPORT_DIR, "Export"
    )


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


def get_export_job_ttl() -> int:
    """Return how long (in seconds) a finished background export's file and job record are kept.

    Reads ``ckanext.tables.export.job_ttl``. Defaults to 3600 (1 hour). Swept
    by ``ckan tables clean-exports``, not automatically — nothing deletes a
    background export's file just because this TTL has passed until that
    command runs.
    """
    return tk.config.get(CONF_EXPORT_JOB_TTL, DEFAULT_EXPORT_JOB_TTL)
