import os
import stat
import tempfile
from unittest import mock

from ckanext.tables import config


class TestGetCacheDir:
    def test_returns_existing_private_dir(self, tmp_path):

        with mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: str(tmp_path)}):
            result = config.get_cache_dir()
            assert result == str(tmp_path)

    def test_creates_dir_if_not_exists(self, tmp_path):
        new_dir = str(tmp_path / "new_cache_dir")
        assert not os.path.exists(new_dir)
        with mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: new_dir}):
            result = config.get_cache_dir()
            assert os.path.isdir(result)

    def test_created_dir_is_private(self, tmp_path):
        """A freshly created cache dir must be mode 0700 (owner-only)."""
        new_dir = str(tmp_path / "new_cache_dir")
        with mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: new_dir}):
            result = config.get_cache_dir()

        mode = stat.S_IMODE(os.stat(result).st_mode)
        assert mode == 0o700

    def test_returns_none_when_dir_cannot_be_created(self, tmp_path):
        non_writable = str(tmp_path / "no_permission")
        with (
            mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: non_writable}),
            mock.patch("os.makedirs", side_effect=OSError("Permission denied")),
        ):
            result = config.get_cache_dir()

        assert result is None

    def test_refuses_group_or_world_writable_dir(self, tmp_path):
        """A pre-existing directory that other local users could write to must be refused.

        This is the SEC-5 attack surface: a shared/writable cache directory lets another
        local user plant a file at the predictable, hash-derived cache path.
        """
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        with mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: str(unsafe_dir)}):
            result = config.get_cache_dir()

        assert result is None

    def test_refuses_dir_owned_by_another_user(self, tmp_path):
        other_user_dir = tmp_path / "not-mine"
        other_user_dir.mkdir()
        other_user_dir.chmod(0o700)

        with (
            mock.patch.object(config.tk, "config", {config.CONF_CACHE_DIR: str(other_user_dir)}),
            mock.patch.object(config.os, "getuid", return_value=os.getuid() + 1),
        ):
            result = config.get_cache_dir()

        assert result is None

    def test_explicit_cache_dir_argument_is_also_validated(self, tmp_path):
        """The *cache_dir* argument bypasses config lookup but not the safety check."""
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        assert config.get_cache_dir(str(unsafe_dir)) is None

    def test_default_uses_ckan_storage_path(self):
        with mock.patch.object(config.tk, "config", {"ckan.storage_path": "/srv/ckan"}):
            assert config._default_cache_dir() == os.path.join("/srv/ckan", "tables-cache")

    def test_default_falls_back_to_tempdir_without_storage_path(self):
        with mock.patch.object(config.tk, "config", {}):
            assert config._default_cache_dir() == os.path.join(tempfile.gettempdir(), "tables-cache")
