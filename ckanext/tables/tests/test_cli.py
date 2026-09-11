import os
import time
from unittest import mock

import pandas as pd
from click.testing import CliRunner

from ckanext.tables.cache import FeatherCacheBackend
from ckanext.tables.cli import clean_cache, tables


class TestCliDiscovery:
    def test_tables_group_is_discovered_via_blanket_cli(self):
        from ckanext.tables.plugin import TablesPlugin

        commands = TablesPlugin.get_commands(TablesPlugin())
        assert any(c.name == "tables" for c in commands)

    def test_clean_cache_is_registered_on_the_group(self):
        assert "clean-cache" in tables.commands
        assert tables.commands["clean-cache"] is clean_cache


class TestCleanCacheCommand:
    def test_reports_removed_count(self, tmp_path):
        backend = FeatherCacheBackend(cache_dir=str(tmp_path))
        backend.set("stale", pd.DataFrame([{"a": 1}]), ttl=1)
        old_mtime = time.time() - 10
        os.utime(backend._meta_path("stale"), (old_mtime, old_mtime))

        runner = CliRunner()
        with mock.patch("ckanext.tables.cli.get_cache_backend", return_value=backend):
            result = runner.invoke(tables, ["clean-cache"])

        assert result.exit_code == 0
        assert "Removed 1 expired cache file" in result.output

    def test_reports_nothing_to_clean(self, tmp_path):
        backend = FeatherCacheBackend(cache_dir=str(tmp_path))

        runner = CliRunner()
        with mock.patch("ckanext.tables.cli.get_cache_backend", return_value=backend):
            result = runner.invoke(tables, ["clean-cache"])

        assert result.exit_code == 0
        assert "No expired cache entries found." in result.output
