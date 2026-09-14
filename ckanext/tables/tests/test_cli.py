import json
import os
import time
from unittest import mock

import pandas as pd
from click.testing import CliRunner

from ckanext.tables.cache import FeatherCacheBackend
from ckanext.tables.cli import clean_cache, clean_exports, tables


class TestCliDiscovery:
    def test_tables_group_is_discovered_via_blanket_cli(self):
        from ckanext.tables.plugin import TablesPlugin

        commands = TablesPlugin.get_commands(TablesPlugin())
        assert any(c.name == "tables" for c in commands)

    def test_clean_cache_is_registered_on_the_group(self):
        assert "clean-cache" in tables.commands
        assert tables.commands["clean-cache"] is clean_cache

    def test_clean_exports_is_registered_on_the_group(self):
        assert "clean-exports" in tables.commands
        assert tables.commands["clean-exports"] is clean_exports


class TestCleanCacheCommand:
    def test_reports_removed_count(self, tmp_path):
        backend = FeatherCacheBackend(cache_dir=str(tmp_path))
        backend.set("stale", pd.DataFrame([{"a": 1}]), ttl=1)
        meta_path = backend._meta_path("stale")
        with open(meta_path) as f:
            meta = json.load(f)
        meta["expires_at"] = time.time() - 10
        with open(meta_path, "w") as f:
            json.dump(meta, f)

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


class TestCleanExportsCommand:
    def _invoke(self, export_dir, ttl=3600):
        runner = CliRunner()
        with (
            mock.patch("ckanext.tables.cli.get_export_dir", return_value=export_dir),
            mock.patch("ckanext.tables.cli.get_export_job_ttl", return_value=ttl),
        ):
            return runner.invoke(tables, ["clean-exports"])

    def test_removes_only_files_older_than_the_ttl(self, tmp_path):
        stale = tmp_path / "stale-job.csv"
        stale.write_text("a,b\n1,2\n")
        fresh = tmp_path / "fresh-job.csv"
        fresh.write_text("a,b\n1,2\n")

        old_time = time.time() - 7200
        os.utime(stale, (old_time, old_time))

        result = self._invoke(str(tmp_path), ttl=3600)

        assert result.exit_code == 0
        assert "Removed 1 expired export file" in result.output
        assert not stale.exists()
        assert fresh.exists()

    def test_reports_nothing_to_clean(self, tmp_path):
        result = self._invoke(str(tmp_path))

        assert result.exit_code == 0
        assert "No expired export files found." in result.output

    def test_reports_when_no_export_dir_is_configured(self):
        result = self._invoke(None)

        assert result.exit_code == 0
        assert "No export directory is configured or usable" in result.output
