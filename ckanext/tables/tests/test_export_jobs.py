from unittest import mock

import pytest

import ckan.plugins.toolkit as tk

from ckanext.tables.data_sources import ListDataSource
from ckanext.tables.export_jobs import (
    _ensure_request_context,
    _get_exporter,
    _rebuild_params,
    _rebuild_table,
    _resolve_table_class,
    check_export_locator_access,
    run_export_job,
)
from ckanext.tables.exporters import CSVExporter, JSONExporter
from ckanext.tables.table import ColumnDefinition, TableDefinition
from ckanext.tables.types import FilterItem, QueryParams


@pytest.fixture
def sample_table() -> TableDefinition:
    return TableDefinition(
        name="people",
        data_source=ListDataSource([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]),
        columns=[ColumnDefinition(field="name"), ColumnDefinition(field="age")],
        exporters=[CSVExporter, JSONExporter],
    )


class _DemoGenericTable(TableDefinition):
    """Module-level (so dotted-path-resolvable) stand-in for a GenericTableView table."""

    def __init__(self):
        super().__init__(name="demo", data_source=ListDataSource([{"a": 1}]))

    @classmethod
    def check_access(cls, context):
        pass


class _RestrictedGenericTable(TableDefinition):
    @classmethod
    def check_access(cls, context):
        raise tk.NotAuthorized


def _dotted(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


class TestRebuildParams:
    def test_round_trips_filters_sort(self):
        params = _rebuild_params(
            {
                "filters": [{"field": "age", "operator": "=", "value": "30"}],
                "sort_by": "age",
                "sort_order": "desc",
            }
        )

        assert params == QueryParams(
            filters=[FilterItem("age", "=", "30")],
            sort_by="age",
            sort_order="desc",
        )

    def test_defaults_for_missing_keys(self):
        assert _rebuild_params({}) == QueryParams(filters=[], sort_by=None, sort_order=None)


class TestGetExporter:
    def test_returns_the_named_exporter(self, sample_table):
        assert _get_exporter(sample_table, "csv") is CSVExporter

    def test_raises_for_an_unknown_exporter(self, sample_table):
        with pytest.raises(ValueError, match="Unknown exporter"):
            _get_exporter(sample_table, "does-not-exist")


class TestRebuildTable:
    def test_resource_view_locator_delegates_to_the_shared_lookup(self, sample_table):
        resource = {"id": "res-1"}
        resource_view = {"id": "view-1", "resource_id": "res-1"}

        with (
            mock.patch(
                "ckanext.tables.export_jobs.tables_get_resource_and_view",
                return_value=(resource, resource_view),
            ) as mock_lookup,
            mock.patch(
                "ckanext.tables.export_jobs.tables_init_temporary_preview_table",
                return_value=sample_table,
            ) as mock_init,
        ):
            result = _rebuild_table({"kind": "resource_view", "resource_id": "res-1", "resource_view_id": "view-1"})

        mock_lookup.assert_called_once_with("res-1", "view-1")
        mock_init.assert_called_once_with(resource, resource_view, 0)
        assert result is sample_table

    def test_resource_view_locator_passes_through_its_sheet_index(self, sample_table):
        resource = {"id": "res-1"}
        resource_view = {"id": "view-1", "resource_id": "res-1"}

        with (
            mock.patch(
                "ckanext.tables.export_jobs.tables_get_resource_and_view",
                return_value=(resource, resource_view),
            ),
            mock.patch(
                "ckanext.tables.export_jobs.tables_init_temporary_preview_table",
                return_value=sample_table,
            ) as mock_init,
        ):
            _rebuild_table(
                {"kind": "resource_view", "resource_id": "res-1", "resource_view_id": "view-1", "sheet_index": 2}
            )

        mock_init.assert_called_once_with(resource, resource_view, 2)

    def test_generic_locator_resolves_and_instantiates_the_table_class(self):
        result = _rebuild_table({"kind": "generic", "table_class": _dotted(_DemoGenericTable)})

        assert isinstance(result, _DemoGenericTable)

    def test_unsupported_locator_kind_raises(self):
        with pytest.raises(ValueError, match="Unsupported export locator kind"):
            _rebuild_table({"kind": "unknown"})

    def test_missing_kind_raises(self):
        with pytest.raises(ValueError, match="Unsupported export locator kind"):
            _rebuild_table({})


class TestResolveTableClass:
    def test_resolves_a_module_level_class_by_its_dotted_path(self):
        assert _resolve_table_class(_dotted(_DemoGenericTable)) is _DemoGenericTable

    def test_raises_for_an_unimportable_module(self):
        with pytest.raises(ValueError, match="does not resolve to a TableDefinition"):
            _resolve_table_class("no.such.module.SomeTable")

    def test_raises_for_a_missing_class_in_a_real_module(self):
        with pytest.raises(ValueError, match="does not resolve to a TableDefinition"):
            _resolve_table_class("ckanext.tables.tests.test_export_jobs.NoSuchTable")

    def test_raises_when_the_resolved_object_is_not_a_table_definition(self):
        with pytest.raises(ValueError, match="does not resolve to a TableDefinition"):
            _resolve_table_class("ckanext.tables.tests.test_export_jobs._dotted")


class TestCheckExportLocatorAccess:
    def test_resource_view_locator_delegates_to_the_shared_lookup(self):
        with mock.patch("ckanext.tables.export_jobs.tables_get_resource_and_view") as mock_lookup:
            check_export_locator_access({"kind": "resource_view", "resource_id": "res-1", "resource_view_id": "view-1"})

        mock_lookup.assert_called_once_with("res-1", "view-1")

    def test_generic_locator_allows_when_the_resolved_class_allows(self):
        # _DemoGenericTable.check_access is a no-op — this must not raise.
        check_export_locator_access({"kind": "generic", "table_class": _dotted(_DemoGenericTable)})

    def test_generic_locator_denies_when_the_resolved_class_denies(self):
        with (
            mock.patch("ckanext.tables.export_jobs.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            check_export_locator_access({"kind": "generic", "table_class": _dotted(_RestrictedGenericTable)})

        assert mock_abort.call_args[0][0] == 403

    def test_unknown_kind_is_treated_as_not_found(self):
        with (
            mock.patch("ckanext.tables.export_jobs.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            check_export_locator_access({"kind": "unknown"})

        assert mock_abort.call_args[0][0] == 404


class TestEnsureRequestContext:
    # A real RQ worker has no Flask application context — unlike every other
    # path into this codebase, which runs inside a real CKAN request.

    def test_builds_and_pushes_an_app_when_none_is_active(self):
        fake_app = mock.Mock()
        fake_request_ctx = mock.MagicMock()
        fake_app.test_request_context.return_value = fake_request_ctx

        with (
            mock.patch("ckanext.tables.export_jobs.has_request_context", return_value=False),
            mock.patch(
                "ckanext.tables.export_jobs.ckan.config.middleware.make_app", return_value=fake_app
            ) as mock_make_app,
            _ensure_request_context(),
        ):
            pass

        mock_make_app.assert_called_once()
        fake_app.test_request_context.assert_called_once()
        fake_request_ctx.__enter__.assert_called_once()
        fake_request_ctx.__exit__.assert_called_once()

    @pytest.mark.usefixtures("with_request_context")
    def test_does_not_build_a_second_app_when_a_request_context_is_already_active(self):
        with (
            mock.patch("ckanext.tables.export_jobs.ckan.config.middleware.make_app") as mock_make_app,
            _ensure_request_context(),
        ):
            pass

        assert not mock_make_app.called


@pytest.mark.usefixtures("with_request_context")
class TestRunExportJob:
    def _locator(self):
        return {"kind": "resource_view", "resource_id": "res-1", "resource_view_id": "view-1"}

    def test_success_writes_the_file_and_returns_its_metadata(self, sample_table, tmp_path):
        with mock.patch("ckanext.tables.export_jobs._rebuild_table", return_value=sample_table):
            result = run_export_job(self._locator(), "csv", {}, str(tmp_path))

        assert result["success"] is True
        assert result["mime_type"] == CSVExporter.mime_type
        assert result["filename"] == f"people.{CSVExporter.name}"

        written = (tmp_path / result["disk_filename"]).read_bytes()
        assert b"Alice" in written
        assert b"Bob" in written

    def test_disk_filename_uses_the_job_id_not_the_table_name(self, sample_table, tmp_path):
        fake_job = mock.Mock(id="job-xyz")
        with (
            mock.patch("ckanext.tables.export_jobs._rebuild_table", return_value=sample_table),
            mock.patch("ckanext.tables.export_jobs.rq.get_current_job", return_value=fake_job),
        ):
            result = run_export_job(self._locator(), "csv", {}, str(tmp_path))

        assert result["disk_filename"] == "job-xyz.csv"
        assert (tmp_path / "job-xyz.csv").exists()

    def test_unknown_exporter_fails_cleanly_without_leaking_the_exception(self, sample_table, tmp_path):
        with mock.patch("ckanext.tables.export_jobs._rebuild_table", return_value=sample_table):
            result = run_export_job(self._locator(), "does-not-exist", {}, str(tmp_path))

        assert result["success"] is False
        assert "does-not-exist" not in result["error"]
        assert result["error"]

    def test_unresolvable_table_fails_cleanly(self, tmp_path):
        with mock.patch("ckanext.tables.export_jobs._rebuild_table", side_effect=RuntimeError("resource is gone")):
            result = run_export_job(self._locator(), "csv", {}, str(tmp_path))

        assert result["success"] is False
        assert "resource is gone" not in result["error"]

    def test_filters_and_sort_are_applied(self, sample_table, tmp_path):
        with mock.patch("ckanext.tables.export_jobs._rebuild_table", return_value=sample_table):
            result = run_export_job(
                self._locator(),
                "json",
                {"filters": [{"field": "name", "operator": "=", "value": "Alice"}]},
                str(tmp_path),
            )

        written = (tmp_path / result["disk_filename"]).read_text()
        assert "Alice" in written
        assert "Bob" not in written
