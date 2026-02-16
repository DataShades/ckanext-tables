import os
import shutil

import pytest

from ckanext.tables import config


@pytest.fixture
def clear_cache():
    """Fixture to provide a temporary cache directory."""
    cache_dir = config.get_cache_dir()

    clear_directory(cache_dir)

    yield cache_dir

    clear_directory(cache_dir)


def clear_directory(path):
    if not os.path.exists(path):
        os.mkdir(path)

    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)

        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
