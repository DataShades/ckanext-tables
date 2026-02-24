from unittest import mock

import pytest

from ckanext.tables import formatters
from ckanext.tables.data_sources import ListDataSource
from ckanext.tables.table import (
    BulkActionDefinition,
    ColumnDefinition,
    RowActionDefinition,
    TableActionDefinition,
    TableDefinition,
)
from ckanext.tables.types import FilterItem, QueryParams


class TestColumnDefinition:
    def test_auto_title_from_field(self):
        col = ColumnDefinition(field="first_name")
        assert col.title == "First Name"

    def test_explicit_title(self):
        col = ColumnDefinition(field="x", title="MyTitle")
        assert col.title == "MyTitle"

    def test_to_dict_basic(self):
        col = ColumnDefinition(field="age")
        d = col.to_dict()
        assert d["field"] == "age"
        assert d["visible"] is True
        assert "headerFilter" in d  # filterable by default

    def test_to_dict_not_filterable(self):
        col = ColumnDefinition(field="id", filterable=False)
        d = col.to_dict()
        assert "headerFilter" not in d

    def test_to_dict_not_sortable(self):
        col = ColumnDefinition(field="id", sortable=False)
        d = col.to_dict()
        assert d.get("headerSort") is False
        assert "sorter" not in d

    def test_to_dict_with_width(self):
        col = ColumnDefinition(field="id", width=120)
        d = col.to_dict()
        assert d["width"] == 120

    def test_to_dict_with_tabulator_formatter(self):
        col = ColumnDefinition(field="id", tabulator_formatter="html")
        d = col.to_dict()
        assert d["formatter"] == "html"

    def test_to_dict_with_min_width(self):
        col = ColumnDefinition(field="id", min_width=50)
        d = col.to_dict()
        assert d["minWidth"] == 50


@pytest.mark.usefixtures("with_request_context")
class TestTableDefinitionBasic:
    def test_get_raw_data_returns_all_rows(self, simple_table):
        data = simple_table.get_raw_data(QueryParams(), paginate=False)
        assert len(data) == 3

    def test_get_raw_data_with_pagination(self, simple_table):
        data = simple_table.get_raw_data(QueryParams(page=1, size=2))
        assert len(data) == 2

    def test_get_total_count(self, simple_table):
        assert simple_table.get_total_count(QueryParams()) == 3

    def test_get_total_count_with_filter(self, simple_table):
        params = QueryParams(filters=[FilterItem(field="name", operator="=", value="Alice")])
        assert simple_table.get_total_count(params) == 1

    def test_get_tabulator_config_keys(self, simple_table):
        cfg = simple_table.get_tabulator_config()
        assert "columns" in cfg
        assert "placeholder" in cfg
        assert "pagination" in cfg

    def test_get_tabulator_config_with_ajax_url(self, simple_table):
        simple_table.ajax_url = "http://example.com/ajax"
        cfg = simple_table.get_tabulator_config()
        assert cfg["ajaxURL"] == "http://example.com/ajax"

    def test_get_tabulator_config_without_ajax_url(self, simple_table):
        assert "ajaxURL" not in simple_table.get_tabulator_config()

    def test_unique_id_generated(self, simple_data):
        t1 = TableDefinition(name="t", data_source=ListDataSource(simple_data))
        t2 = TableDefinition(name="t", data_source=ListDataSource(simple_data))
        assert t1.id != t2.id

    def test_default_placeholder(self, simple_table):
        assert simple_table.placeholder is not None

    def test_get_exporter_found(self, simple_table):
        from ckanext.tables.exporters import CSVExporter, JSONExporter

        simple_table.exporters = [CSVExporter, JSONExporter]
        assert simple_table.get_exporter("csv") is CSVExporter
        assert simple_table.get_exporter("json") is JSONExporter

    def test_get_exporter_not_found(self, simple_table):
        assert simple_table.get_exporter("nonexistent") is None


@pytest.mark.usefixtures("with_request_context")
class TestTableDefinitionActions:
    def test_bulk_action_config_adds_row_header(self, simple_data):
        """__init__ adds the rowHeader only when bulk_actions are passed at construction."""
        tbl = TableDefinition(
            name="bulk_tbl",
            data_source=ListDataSource(simple_data),
            bulk_actions=[
                BulkActionDefinition(action="delete", label="Delete", callback=lambda rows: {"success": True})
            ],
        )
        assert "rowHeader" in tbl.get_tabulator_config()

    def test_row_actions_appends_actions_column(self, simple_data):
        """__init__ appends __table_actions column when row_actions are provided."""
        tbl = TableDefinition(
            name="row_act_tbl",
            data_source=ListDataSource(simple_data),
            row_actions=[RowActionDefinition(action="view", label="View", callback=lambda row: {"success": True})],
        )
        assert "__table_actions" in [col.field for col in tbl.columns]

    def test_get_row_action_found(self, simple_table):
        action = RowActionDefinition(action="edit", label="Edit", callback=lambda row: {"success": True})
        simple_table.row_actions.append(action)
        assert simple_table.get_row_action("edit") is action

    def test_get_row_action_not_found(self, simple_table):
        assert simple_table.get_row_action("nonexistent") is None

    def test_get_bulk_action_found(self, simple_table):
        action = BulkActionDefinition(action="export", label="Export", callback=lambda rows: {"success": True})
        simple_table.bulk_actions.append(action)
        assert simple_table.get_bulk_action("export") is action

    def test_get_bulk_action_not_found(self, simple_table):
        assert simple_table.get_bulk_action("nonexistent") is None

    def test_get_table_action_found(self, simple_table):
        action = TableActionDefinition(action="refresh", label="Refresh", callback=lambda: {"success": True})
        simple_table.table_actions.append(action)
        assert simple_table.get_table_action("refresh") is action

    def test_get_table_action_not_found(self, simple_table):
        assert simple_table.get_table_action("nonexistent") is None

    def test_row_action_callable(self):
        callback = mock.Mock(return_value={"success": True})
        action = RowActionDefinition(action="do", label="Do", callback=callback)
        action({"id": 1})
        callback.assert_called_once_with({"id": 1})

    def test_bulk_action_callable(self):
        callback = mock.Mock(return_value={"success": True})
        action = BulkActionDefinition(action="bulk_do", label="Bulk", callback=callback)
        action([{"id": 1}, {"id": 2}])
        callback.assert_called_once()

    def test_table_action_callable(self):
        callback = mock.Mock(return_value={"success": True})
        action = TableActionDefinition(action="act", label="Act", callback=callback)
        action()
        callback.assert_called_once()

    def test_get_row_actions_dict(self, simple_table):
        action = RowActionDefinition(action="view", label="View", callback=lambda row: {"success": True}, icon="fa-eye")
        simple_table.row_actions.append(action)
        row_actions = simple_table.get_row_actions()
        assert "view" in row_actions
        assert row_actions["view"]["icon"] == "fa-eye"


@pytest.mark.usefixtures("with_request_context")
class TestTableDefinitionFormatters:
    def test_apply_formatters_boolean(self):
        tbl = TableDefinition(
            name="fmt_tbl",
            data_source=ListDataSource([{"active": True}]),
            columns=[
                ColumnDefinition(
                    field="active",
                    formatters=[(formatters.BooleanFormatter, {})],
                )
            ],
        )
        data = tbl.get_data(QueryParams())
        assert data[0]["active"] == "Yes"

    def test_apply_formatters_trim_string(self):
        tbl = TableDefinition(
            name="trim_tbl",
            data_source=ListDataSource([{"name": "A" * 100}]),
            columns=[
                ColumnDefinition(
                    field="name",
                    formatters=[(formatters.TrimStringFormatter, {"max_length": 10})],
                )
            ],
        )
        data = tbl.get_data(QueryParams())
        assert data[0]["name"] == "A" * 10 + "..."


@pytest.mark.usefixtures("with_request_context", "clean_redis")
class TestTableDefinitionCacheIntegration:
    def test_refresh_data_no_error(self, simple_data):
        from ckanext.tables.cache import RedisCacheBackend
        from ckanext.tables.data_sources import CsvUrlDataSource

        with mock.patch("ckanext.tables.data_sources.pd.read_csv") as mock_read:
            import pandas as pd

            mock_read.return_value = pd.DataFrame(simple_data)
            ds = CsvUrlDataSource(url="http://example.com/data.csv", cache_backend=RedisCacheBackend())

        tbl = TableDefinition(name="cached_tbl", data_source=ds)
        tbl.refresh_data()  # should not raise even if cache is empty

    def test_table_without_cache_returns_none_count(self, simple_table):
        assert simple_table._get_cached_count(QueryParams()) is None

    def test_count_caching_returns_consistent_value(self, simple_data):
        from ckanext.tables.cache import RedisCacheBackend
        from ckanext.tables.data_sources import CsvUrlDataSource

        with mock.patch("ckanext.tables.data_sources.pd.read_csv") as mock_read:
            import pandas as pd

            mock_read.return_value = pd.DataFrame(simple_data)
            ds = CsvUrlDataSource(url="http://example.com/c.csv", cache_backend=RedisCacheBackend())
            ds._df = pd.DataFrame(simple_data)
            ds._filtered_df = pd.DataFrame(simple_data)

        tbl = TableDefinition(name="count_cache_tbl", data_source=ds)
        params = QueryParams()
        assert tbl.get_total_count(params) == tbl.get_total_count(params)
