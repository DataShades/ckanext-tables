import os
import tempfile
from unittest import mock


class TestGetCacheDir:
    def test_returns_existing_dir(self, tmp_path):
        from ckanext.tables import config

        with mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: str(tmp_path)}):
            result = config.get_cache_dir()
            assert result == str(tmp_path)

    def test_creates_dir_if_not_exists(self, tmp_path):
        from ckanext.tables import config

        new_dir = str(tmp_path / "new_cache_dir")
        assert not os.path.exists(new_dir)
        with mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: new_dir}):
            result = config.get_cache_dir()
            assert os.path.isdir(result)

    def test_falls_back_to_tempdir_on_os_error(self, tmp_path):
        from ckanext.tables import config

        non_writable = str(tmp_path / "no_permission")
        with (
            mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: non_writable}),
            mock.patch("os.makedirs", side_effect=OSError("Permission denied")),
        ):
            result = config.get_cache_dir()
            assert result == tempfile.gettempdir()
