import os
import tempfile

import ckan.plugins.toolkit as tk

CONF_CACHE_DIR = "ckanext.tables.cache_dir"


def get_cache_dir() -> str:
    cache_dir = tk.config[CONF_CACHE_DIR]

    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir)
        except OSError:
            cache_dir = tempfile.gettempdir()

    return cache_dir
