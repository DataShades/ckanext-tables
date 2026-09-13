import json
from unittest import mock

import pytest

import ckan.plugins.toolkit as tk

from ckanext.tables.data_sources import DataSourceError, ListDataSource
from ckanext.tables.exporters import CSVExporter, JSONExporter, XLSXExporter
from ckanext.tables.generics import AjaxTableMixin, ExportTableMixin, GenericTableView
from ckanext.tables.table import (
    BulkActionDefinition,
    ColumnDefinition,
    RowActionDefinition,
    TableActionDefinition,
    TableDefinition,
)
from ckanext.tables.types import QueryParams


@pytest.fixture
def sample_table(simple_data: list[dict[str, str | int]]) -> TableDefinition:
    """Full-featured table with success and exception variants of every action type."""
    return TableDefinition(
        name="sample",
        data_source=ListDataSource(simple_data),
        columns=[
            ColumnDefinition(field="name", title="Name"),
            ColumnDefinition(field="age", title="Age"),
        ],
        exporters=[CSVExporter, JSONExporter, XLSXExporter],
        table_actions=[
            TableActionDefinition(
                action="my_action",
                label="Action",
                callback=mock.Mock(return_value={"success": True}),
            ),
            TableActionDefinition(
                action="fail_action",
                label="Fail",
                callback=mock.Mock(side_effect=RuntimeError("boom")),
            ),
        ],
        row_actions=[
            RowActionDefinition(
                action="view",
                label="View",
                callback=mock.Mock(return_value={"success": True}),
            ),
            RowActionDefinition(
                action="fail_row",
                label="Fail Row",
                callback=mock.Mock(side_effect=RuntimeError("row boom")),
            ),
        ],
        bulk_actions=[
            BulkActionDefinition(
                action="bulk_delete",
                label="Delete",
                callback=mock.Mock(return_value={"success": True}),
            ),
            BulkActionDefinition(
                action="bulk_fail",
                label="Fail",
                callback=mock.Mock(side_effect=RuntimeError("bulk boom")),
            ),
        ],
    )


@pytest.mark.usefixtures("with_request_context")
class TestAjaxTableMixin:
    def _make_mixin(self):
        class ConcreteView(AjaxTableMixin):
            pass

        return ConcreteView()

    def test_ajax_data_response(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.tables_build_params") as mock_params:
            mock_params.return_value = QueryParams(page=1, size=10)
            response = mixin._ajax_data(sample_table)
        data = json.loads(response.get_data(as_text=True))
        assert "data" in data
        assert "last_page" in data
        assert "total" in data
        assert data["total"] == 3

    def test_ajax_data_returns_502_on_data_source_error(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with (
            mock.patch("ckanext.tables.generics.tables_build_params") as mock_params,
            mock.patch.object(sample_table, "get_data", side_effect=DataSourceError("boom")),
        ):
            mock_params.return_value = QueryParams(page=1, size=10)
            response, status = mixin._ajax_data(sample_table)

        assert status == 502
        assert "error" in json.loads(response.get_data(as_text=True))

    def test_apply_table_action_not_found(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_table_action(sample_table, "nonexistent")
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_table_action_success(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_table_action(sample_table, "my_action")
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is True

    def test_apply_table_action_exception(self, sample_table: TableDefinition):
        # The raw exception message must never reach the client — it can embed
        # user-controlled data and is rendered on the page as-is by the frontend.
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.log"):
            response = mixin._apply_table_action(sample_table, "fail_action")
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False
        assert "boom" not in str(data.get("errors", ""))
        assert data.get("errors")

    def test_apply_row_action_not_found(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_row_action(sample_table, "nonexistent", '{"id": 1}')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_row_action_no_row(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_row_action(sample_table, "view", None)
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_row_action_no_action(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_row_action(sample_table, "", '{"id": 1}')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_row_action_success(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_row_action(sample_table, "view", '{"name": "Alice"}')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is True

    def test_apply_row_action_exception(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.log"):
            response = mixin._apply_row_action(sample_table, "fail_row", '{"name": "Alice"}')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False
        assert "row boom" not in str(data.get("error", ""))
        assert data.get("error")

    def test_apply_bulk_action_not_found(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_bulk_action(sample_table, "nonexistent", '[{"id": 1}]')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_bulk_action_no_rows(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_bulk_action(sample_table, "bulk_delete", None)
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_bulk_action_malformed_rows_does_not_500(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.log"):
            response = mixin._apply_bulk_action(sample_table, "bulk_delete", "not valid json")
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_apply_bulk_action_success(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._apply_bulk_action(sample_table, "bulk_delete", '[{"name": "Alice"}]')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is True

    def test_apply_bulk_action_exception(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.log"):
            response = mixin._apply_bulk_action(sample_table, "bulk_fail", '[{"name": "Alice"}]')
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False
        assert "bulk boom" not in str(data.get("error", ""))
        assert data.get("error")

    # --- refresh ---

    def test_refresh_data(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        response = mixin._refresh_data(sample_table)
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is True


@pytest.mark.usefixtures("with_request_context")
class TestExportTableMixin:
    def _make_mixin(self):
        class ConcreteExport(ExportTableMixin):
            pass

        return ConcreteExport()

    def test_export_not_found_aborts(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.tk.abort") as mock_abort:
            mock_abort.side_effect = Exception("404")
            with pytest.raises(Exception, match="404"):
                mixin._export(sample_table, "nonexistent_exporter")

    def test_export_missing_dependency_aborts_501(self, sample_table: TableDefinition):
        # Must be checked before the streamed Response is built — by the time
        # export() would raise inside the generator body, headers (and the 200
        # status) are already committed and can no longer be changed.
        mixin = self._make_mixin()
        with (
            mock.patch.object(XLSXExporter, "is_available", return_value=False),
            mock.patch("ckanext.tables.generics.tk.abort") as mock_abort,
        ):
            mock_abort.side_effect = Exception("501")
            with pytest.raises(Exception, match="501"):
                mixin._export(sample_table, "xlsx")

        assert mock_abort.call_args[0][0] == 501

    def test_export_csv(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.tables_build_params") as mock_params:
            mock_params.return_value = QueryParams()
            response = mixin._export(sample_table, "csv")
        assert "text/csv" in response.content_type
        assert b"Name" in response.data

    def test_export_json(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.tables_build_params") as mock_params:
            mock_params.return_value = QueryParams()
            response = mixin._export(sample_table, "json")
        assert response.content_type == "application/json"
        data = json.loads(response.data)
        assert isinstance(data, list)

    def test_export_over_row_cap_aborts_without_exporting(self, sample_table: TableDefinition):
        """A result set larger than the configured cap must be rejected (413), not exported."""
        mixin = self._make_mixin()
        with (
            mock.patch("ckanext.tables.generics.get_export_max_rows", return_value=1),
            mock.patch("ckanext.tables.generics.tk.abort") as mock_abort,
            mock.patch.object(CSVExporter, "export_stream") as mock_export_stream,
        ):
            mock_abort.side_effect = Exception("413")
            with pytest.raises(Exception, match="413"):
                mixin._export(sample_table, "csv")

        assert mock_abort.call_args[0][0] == 413
        assert not mock_export_stream.called

    def test_export_at_row_cap_is_allowed(self, sample_table: TableDefinition):
        """simple_data has exactly 3 rows — a cap of 3 must still allow the export."""
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.get_export_max_rows", return_value=3):
            response = mixin._export(sample_table, "csv")
        assert "text/csv" in response.content_type

    def test_prepare_export_filename(self, sample_table: TableDefinition):
        mixin = self._make_mixin()
        filename = mixin._prepare_export_filename(sample_table, CSVExporter)
        assert "sample" in filename
        assert filename.endswith(".csv")

    def test_export_content_disposition_is_quoted(self, sample_table: TableDefinition):
        """The filename contains a space (timestamp) so it must be quoted."""
        mixin = self._make_mixin()
        with mock.patch("ckanext.tables.generics.tables_build_params") as mock_params:
            mock_params.return_value = QueryParams()
            response = mixin._export(sample_table, "csv")

        disposition = response.headers["Content-Disposition"]
        assert disposition.startswith(f'attachment; filename="{sample_table.name}-')
        assert disposition.endswith('.csv"')


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "with_request_context")
class TestGenericTableView:
    @pytest.fixture
    def view(self, sample_table: TableDefinition):
        """A GenericTableView whose inner table reuses the sample_table fixture data."""
        # Capture fixture values for use inside the nested class
        _data_source = sample_table.data_source
        _columns = sample_table.columns
        _exporters = sample_table.exporters
        _table_actions = sample_table.table_actions

        class MyTable(TableDefinition):
            def __init__(self):
                super().__init__(
                    name="my_table",
                    data_source=_data_source,
                    columns=_columns,
                    exporters=_exporters,
                    table_actions=_table_actions,
                )

            @classmethod
            def check_access(cls, context):
                pass  # always allow

        return GenericTableView(table=MyTable)

    def test_check_access_allowed(self, view):
        assert view.check_access() is True

    def test_check_access_denied(self, simple_data: list[dict[str, str | int]]):
        class RestrictedTable(TableDefinition):
            def __init__(self):
                super().__init__(
                    name="restricted",
                    data_source=ListDataSource(simple_data),
                )

            @classmethod
            def check_access(cls, context):
                raise tk.NotAuthorized

        assert GenericTableView(table=RestrictedTable).check_access() is False

    def test_dispatch_post_no_action(self, view, app):
        tbl = view.table()
        with app.flask_app.test_request_context("/", method="POST", data={}):
            response = view._dispatch_post(tbl)
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is False

    def test_dispatch_post_table_action(self, view, app):
        tbl = view.table()
        with app.flask_app.test_request_context("/", method="POST", data={"table_action": "my_action"}):
            response = view._dispatch_post(tbl)
        data = json.loads(response.get_data(as_text=True))
        assert data["success"] is True

    def test_dispatch_get_export(self, view, app):
        tbl = view.table()
        with (
            app.flask_app.test_request_context("/?exporter=csv"),
            mock.patch("ckanext.tables.generics.tables_build_params") as mock_params,
        ):
            mock_params.return_value = QueryParams()
            response = view._dispatch_get(tbl)
        assert "text/csv" in response.content_type

    def test_dispatch_get_ajax(self, view, app):
        tbl = view.table()
        with (
            app.flask_app.test_request_context(
                "/",
                headers={"X-Requested-With": "XMLHttpRequest"},
            ),
            mock.patch("ckanext.tables.generics.tables_build_params") as mock_params,
        ):
            mock_params.return_value = QueryParams()
            response = view._dispatch_get(tbl)
        data = json.loads(response.get_data(as_text=True))
        assert "data" in data
