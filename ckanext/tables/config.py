import os
import tempfile

import ckan.plugins.toolkit as tk

CONF_CACHE_DIR = "ckanext.tables.cache_dir"


def get_cache_dir() -> str:
    default_cache = os.path.join(tempfile.gettempdir(), "ckanext-tables-cache")
    cache_dir = tk.config.get(CONF_CACHE_DIR, default_cache)

    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir)
        except OSError:
            cache_dir = tempfile.gettempdir()

    return cache_dir
