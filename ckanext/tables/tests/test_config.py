import os
import stat
import tempfile
from pathlib import Path
from unittest import mock

import yaml

from ckan.config.declaration import Declaration

from ckanext.tables import config

CONFIG_DECLARATION_PATH = Path(__file__).resolve().parent.parent / "config_declaration.yml"


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

        A shared/writable cache directory would let another local user plant a file
        at the predictable, hash-derived cache path.
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


class TestGetExportDir:
    """get_export_dir shares its safety-check implementation with get_cache_dir.

    See TestGetCacheDir for the exhaustive private-dir/permission/ownership
    cases (_get_private_dir); these just confirm get_export_dir is wired to
    the right config key and default.
    """

    def test_returns_existing_private_dir(self, tmp_path):
        with mock.patch.object(config.tk, "config", {config.CONF_EXPORT_DIR: str(tmp_path)}):
            assert config.get_export_dir() == str(tmp_path)

    def test_creates_dir_if_not_exists(self, tmp_path):
        new_dir = str(tmp_path / "new_export_dir")
        with mock.patch.object(config.tk, "config", {config.CONF_EXPORT_DIR: new_dir}):
            result = config.get_export_dir()

        assert result is not None
        assert os.path.isdir(result)

    def test_refuses_group_or_world_writable_dir(self, tmp_path):
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        with mock.patch.object(config.tk, "config", {config.CONF_EXPORT_DIR: str(unsafe_dir)}):
            assert config.get_export_dir() is None

    def test_default_uses_ckan_storage_path(self):
        with mock.patch.object(config.tk, "config", {"ckan.storage_path": "/srv/ckan"}):
            assert config._default_export_dir() == os.path.join("/srv/ckan", "tables-exports")

    def test_default_falls_back_to_tempdir_without_storage_path(self):
        with mock.patch.object(config.tk, "config", {}):
            assert config._default_export_dir() == os.path.join(tempfile.gettempdir(), "tables-exports")

    def test_default_dir_differs_from_cache_dir(self):
        """A sibling, not a subdirectory — an export job id and a cache key must never collide."""
        with mock.patch.object(config.tk, "config", {"ckan.storage_path": "/srv/ckan"}):
            assert config._default_export_dir() != config._default_cache_dir()


class TestGetExportJobTtl:
    def test_returns_configured_value(self):
        with mock.patch.object(config.tk, "config", {config.CONF_EXPORT_JOB_TTL: 7200}):
            assert config.get_export_job_ttl() == 7200

    def test_defaults_to_one_hour(self):
        with mock.patch.object(config.tk, "config", {}):
            assert config.get_export_job_ttl() == 3600


class TestConfigDeclarationDefaultsAreLiteral:
    """A declaration's ``default`` is applied to the live config verbatim.

    CKAN does ``config[key] = declared_default`` — unlike a value written directly in an
    actual ``.ini`` file, it is never passed through ``ConfigParser`` interpolation,
    so a `%(...)s`-style placeholder in a `default` is applied as that literal
    string, not resolved. This caught ``ckanext.tables.cache.cache_dir`` declaring
    a computed path as its `default`, which produced a directory named exactly
    ``<ckan.storage_path>/tables-cache`` on disk once loaded through CKAN's own
    declaration machinery — guard the whole file against that class of mistake for
    every current and future option.
    """

    def _all_options(self):
        with open(CONFIG_DECLARATION_PATH) as f:
            data = yaml.safe_load(f)

        for group in data.get("groups", []):
            yield from group.get("options", [])

    def test_no_default_looks_like_an_unresolved_placeholder(self):
        for opt in self._all_options():
            default = opt.get("default")
            if not isinstance(default, str):
                continue

            assert "%(" not in default, (
                f"{opt['key']}: `default` contains a %(...)s ConfigParser placeholder, "
                "which CKAN's config declaration never interpolates — use `placeholder` "
                "for a value that must be computed at runtime instead."
            )
            assert "<" not in default, (
                f"{opt['key']}: `default` looks like an unresolved <...> placeholder, "
                "which CKAN applies to the live config as this literal string."
            )

    def test_declared_defaults_are_applied_as_written(self):
        """Load the file through CKAN's own Declaration and check the applied values.

        Every static default should resolve to the exact value used elsewhere in
        this codebase, while cache_dir (computed at runtime — see get_cache_dir)
        should be left unset.
        """
        with open(CONFIG_DECLARATION_PATH) as f:
            data = yaml.safe_load(f)

        decl = Declaration()
        decl.load_dict(data)
        live_config = {}
        decl.make_safe(live_config)

        assert live_config[config.CONF_CACHE_TTL] == config.DEFAULT_CACHE_TTL
        assert live_config[config.CONF_FETCH_CONNECT_TIMEOUT] == config.DEFAULT_FETCH_CONNECT_TIMEOUT
        assert live_config[config.CONF_FETCH_READ_TIMEOUT] == config.DEFAULT_FETCH_READ_TIMEOUT
        assert live_config[config.CONF_FETCH_MAX_BYTES] == config.DEFAULT_FETCH_MAX_BYTES
        assert live_config[config.CONF_MAX_PAGE_SIZE] == config.DEFAULT_MAX_PAGE_SIZE
        assert live_config[config.CONF_EXPORT_MAX_ROWS] == config.DEFAULT_EXPORT_MAX_ROWS
        assert live_config[config.CONF_EXPORT_JOB_TTL] == config.DEFAULT_EXPORT_JOB_TTL

        # The options whose real default is computed in Python, not declared —
        # CKAN must leave them unset (None) so get_cache_dir()/get_export_dir()'s
        # own fallback actually runs.
        assert live_config[config.CONF_CACHE_DIR] is None
        assert live_config[config.CONF_EXPORT_DIR] is None
