import contextlib
import json
import urllib.parse
from unittest import mock

import pandas as pd
import pytest

from ckanext.tables.data_sources import (
    CsvUrlDataSource,
    DataSourceError,
    DataStoreDataSource,
    FeatherUrlDataSource,
    JsonLdUrlDataSource,
    NdjsonUrlDataSource,
    OdsUrlDataSource,
    OrcUrlDataSource,
    ParquetUrlDataSource,
    TsvUrlDataSource,
    XlsUrlDataSource,
    XlsxUrlDataSource,
)
from ckanext.tables.shared import ALL_EXPORTERS
from ckanext.tables.utils import (
    guess_format,
    parse_json_filters,
    parse_tabulator_filters,
    tables_build_params,
    tables_guess_data_source,
    tables_init_temporary_preview_table,
    tables_preview_table_name,
)


class TestParseJsonFilters:
    """A malformed ``filters`` query param must not turn into a 500."""

    def test_valid_filters(self):
        raw = json.dumps([{"field": "age", "operator": "=", "value": "30"}])
        result = parse_json_filters(raw)
        assert len(result) == 1
        assert result[0].field == "age"

    def test_malformed_json_returns_empty(self):
        assert parse_json_filters("not json") == []

    def test_non_list_json_returns_empty(self):
        assert parse_json_filters(json.dumps({"field": "age"})) == []
        assert parse_json_filters(json.dumps("age")) == []
        assert parse_json_filters(json.dumps(42)) == []

    def test_non_object_entry_is_skipped(self):
        raw = json.dumps(["not-an-object", {"field": "age", "operator": "=", "value": "30"}])
        result = parse_json_filters(raw)
        assert len(result) == 1
        assert result[0].field == "age"

    def test_entry_missing_a_key_is_skipped(self):
        raw = json.dumps([{"field": "age", "operator": "="}, {"field": "name", "operator": "=", "value": "Alice"}])
        result = parse_json_filters(raw)
        assert len(result) == 1
        assert result[0].field == "name"


class TestParseTabulatorFilters:
    """Uses real Flask request contexts instead of mocking tk.request."""

    def test_no_filter_params(self, app):
        with app.flask_app.test_request_context("/"):
            result = parse_tabulator_filters()
            assert result == []

    def test_valid_filter_params(self, app):
        qs = "/?filter[0][field]=name&filter[0][type]=like&filter[0][value]=Alice"
        with app.flask_app.test_request_context(qs):
            result = parse_tabulator_filters()
            assert len(result) == 1
            assert result[0].field == "name"
            assert result[0].operator == "like"
            assert result[0].value == "Alice"

    def test_incomplete_filter_ignored(self, app):
        # Missing 'value' — filter should be ignored
        qs = "/?filter[0][field]=name&filter[0][type]=like"
        with app.flask_app.test_request_context(qs):
            result = parse_tabulator_filters()
            assert result == []

    def test_non_filter_key_ignored(self, app):
        with app.flask_app.test_request_context("/?page=1&size=10"):
            result = parse_tabulator_filters()
            assert result == []

    def test_multiple_filters(self, app):
        qs = (
            "/?filter[0][field]=name&filter[0][type]=%3D&filter[0][value]=Alice"
            "&filter[1][field]=age&filter[1][type]=%3E&filter[1][value]=25"
        )
        with app.flask_app.test_request_context(qs):
            result = parse_tabulator_filters()
            assert len(result) == 2


class TestTablesBuildParams:
    """Uses real Flask request contexts instead of mocking tk.request."""

    def test_defaults(self, app):
        with app.flask_app.test_request_context("/"):
            params = tables_build_params()
            assert params.page == 1
            assert params.size == 10
            assert params.filters == []
            assert params.sort_by is None

    def test_custom_page_and_size(self, app):
        with app.flask_app.test_request_context("/?page=3&size=25"):
            params = tables_build_params()
            assert params.page == 3
            assert params.size == 25

    def test_sort_params(self, app):
        qs = "/?sort[0][field]=name&sort[0][dir]=desc"
        with app.flask_app.test_request_context(qs):
            params = tables_build_params()
            assert params.sort_by == "name"
            assert params.sort_order == "desc"

    def test_filters_from_json(self, app):
        filters = json.dumps([{"field": "age", "operator": "=", "value": "30"}])
        qs = f"/?filters={urllib.parse.quote(filters)}"
        with app.flask_app.test_request_context(qs):
            params = tables_build_params()
            assert len(params.filters) == 1
            assert params.filters[0].field == "age"

    def test_zero_size_is_clamped_up(self, app):
        """?size=0 must not reach the ((total + size - 1) // size) division in _ajax_data."""
        with app.flask_app.test_request_context("/?size=0"):
            params = tables_build_params()
            assert params.size == 1

    def test_negative_page_and_size_are_clamped_up(self, app):
        with app.flask_app.test_request_context("/?page=-5&size=-5"):
            params = tables_build_params()
            assert params.page == 1
            assert params.size == 1

    def test_oversized_size_is_clamped_down(self, app):
        with app.flask_app.test_request_context("/?size=100000000"):
            params = tables_build_params()
            from ckanext.tables.config import get_max_page_size

            assert params.size == get_max_page_size()

    def test_size_at_max_page_size_is_unaffected(self, app):
        from ckanext.tables.config import get_max_page_size

        with app.flask_app.test_request_context(f"/?size={get_max_page_size()}"):
            params = tables_build_params()
            assert params.size == get_max_page_size()

    def test_malformed_filters_query_param_does_not_500(self, app):
        qs = f"/?filters={urllib.parse.quote('not valid json')}"
        with app.flask_app.test_request_context(qs):
            params = tables_build_params()
            assert params.filters == []


class TestTablesGuessDataSource:
    def test_csv_format(self):
        resource = {"format": "CSV", "url": "http://example.com/data.csv", "id": "res-1"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, CsvUrlDataSource)

    def test_tsv_format(self):
        resource = {"format": "TSV", "url": "http://example.com/data.tsv", "id": "res-1b"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, TsvUrlDataSource)

    def test_xlsx_format(self):
        resource = {"format": "XLSX", "url": "http://example.com/data.xlsx", "id": "res-2"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, XlsxUrlDataSource)

    def test_xls_format(self):
        resource = {"format": "XLS", "url": "http://example.com/data.xls", "id": "res-2b"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, XlsUrlDataSource)

    def test_ods_format(self):
        resource = {"format": "ODS", "url": "http://example.com/data.ods", "id": "res-2c"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, OdsUrlDataSource)

    def test_jsonld_format(self):
        resource = {"format": "JSONLD", "url": "http://example.com/data.jsonld", "id": "res-2d"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, JsonLdUrlDataSource)

    def test_json_ld_format_with_hyphen(self):
        """Both "JSONLD" and "JSON-LD" are common spellings for a resource's declared format."""
        resource = {"format": "JSON-LD", "url": "http://example.com/download?id=1", "id": "res-2e"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, JsonLdUrlDataSource)

    def test_ndjson_format(self):
        resource = {"format": "NDJSON", "url": "http://example.com/data.ndjson", "id": "res-2f"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, NdjsonUrlDataSource)

    def test_jsonl_format(self):
        """The ".jsonl" ("JSON Lines") extension is another common name for NDJSON."""
        resource = {"format": "JSONL", "url": "http://example.com/data.jsonl", "id": "res-2g"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, NdjsonUrlDataSource)

    def test_orc_format(self):
        resource = {"format": "ORC", "url": "http://example.com/data.orc", "id": "res-3"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, OrcUrlDataSource)

    def test_parquet_format(self):
        resource = {"format": "PARQUET", "url": "http://example.com/data.parquet", "id": "res-4"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, ParquetUrlDataSource)

    def test_feather_format(self):
        resource = {"format": "FEATHER", "url": "http://example.com/data.feather", "id": "res-5"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, FeatherUrlDataSource)

    @pytest.mark.ckan_config("ckan.plugins", "datastore")
    @pytest.mark.usefixtures("clean_datastore", "with_request_context", "with_plugins")
    def test_datastore_active(self):
        resource = {
            "format": "CSV",
            "url": "http://example.com/data.csv",
            "id": "res-6",
            "datastore_active": True,
        }
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, DataStoreDataSource)

    def test_unsupported_format_raises(self):
        resource = {"format": "XML", "url": "http://example.com/data.xml", "id": "res-7"}

        with pytest.raises(DataSourceError, match="Unsupported format"):
            tables_guess_data_source(resource)

    def test_file_url_overrides_resource_url_and_format(self):
        resource = {"format": "CSV", "url": "http://example.com/data.csv", "id": "res-8"}
        resource_view = {"file_url": "http://example.com/upload.xlsx"}
        ds = tables_guess_data_source(resource, resource_view)
        assert isinstance(ds, XlsxUrlDataSource)
        assert ds.url == "http://example.com/upload.xlsx"
        # resource must not be set so get_source_path / get_cache_key use the URL
        assert ds.resource is None

    def test_file_url_strips_query_string_for_format(self):
        resource = {"format": "CSV", "url": "http://example.com/data.csv", "id": "res-9"}
        resource_view = {"file_url": "http://example.com/upload.parquet?token=abc"}
        ds = tables_guess_data_source(resource, resource_view)
        assert isinstance(ds, ParquetUrlDataSource)

    def test_file_url_unsupported_extension_raises(self):
        resource = {"format": "CSV", "url": "http://example.com/data.csv", "id": "res-10"}
        resource_view = {"file_url": "http://example.com/data.xml"}
        with pytest.raises(DataSourceError, match="Unsupported format"):
            tables_guess_data_source(resource, resource_view)

    def test_url_extension_wins_over_stale_format(self):
        resource = {"format": "XLSX", "url": "http://example.com/data.csv", "id": "res-11"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, CsvUrlDataSource)

    def test_url_query_string_does_not_affect_resource_url_format_guess(self):
        resource = {"format": "CSV", "url": "http://example.com/data.parquet?token=abc", "id": "res-12"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, ParquetUrlDataSource)

    def test_url_without_extension_falls_back_to_declared_format(self):
        resource = {"format": "CSV", "url": "http://example.com/download?id=1", "id": "res-13"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, CsvUrlDataSource)


class TestGuessFormat:
    def test_url_extension_takes_priority(self):
        assert guess_format("http://example.com/data.csv", "xlsx") == "csv"

    def test_query_string_is_ignored(self):
        assert guess_format("http://example.com/data.parquet?token=abc") == "parquet"

    def test_falls_back_to_declared_format_without_extension(self):
        assert guess_format("http://example.com/download?id=1", "CSV") == "csv"

    def test_unsupported_extension_is_not_masked_by_declared_format(self):
        assert guess_format("http://example.com/data.xml", "csv") == "xml"

    def test_no_url_and_no_declared_format(self):
        assert guess_format("", "") == ""


@pytest.mark.ckan_config("ckan.plugins", "tables datastore")
@pytest.mark.usefixtures("clean_datastore", "with_plugins", "with_request_context")
class TestTablesInitTemporaryPreviewTable:
    """Routes through DataStoreDataSource so get_columns() doesn't need a network fetch."""

    def _resource(self, rid="res-1"):
        return {"id": rid, "format": "CSV", "url": "http://example.com/data.csv", "datastore_active": True}

    def test_name_and_ajax_url(self):
        tbl = tables_init_temporary_preview_table(self._resource("res-1"), {"id": "view-1"})

        assert tbl.name == "preview_resource_res-1_view-1"
        assert "res-1" in tbl.ajax_url
        assert "view-1" in tbl.ajax_url

    def test_exporters_and_layout(self):
        tbl = tables_init_temporary_preview_table(self._resource("res-2"), {"id": "view-2"})

        assert tbl.exporters == ALL_EXPORTERS
        assert tbl.table_layout == "fitDataStretch"

    def test_columns_come_from_the_data_source(self):
        # No data registered for this resource in the datastore, so get_columns()
        # gracefully returns [] rather than raising — columns should follow suit.
        tbl = tables_init_temporary_preview_table(self._resource("res-3"), {"id": "view-3"})

        assert tbl.columns == []

    def test_file_url_override_changes_the_data_source(self):
        resource = self._resource("res-4")
        resource_view = {"id": "view-4", "file_url": "http://example.com/upload.xlsx"}

        with (
            mock.patch(
                "ckanext.tables.data_sources.fetch_remote_file",
                return_value=contextlib.nullcontext("/tmp/mocked-source"),
            ),
            mock.patch("ckanext.tables.data_sources.pd.read_excel", return_value=pd.DataFrame({"a": [1]})),
        ):
            tbl = tables_init_temporary_preview_table(resource, resource_view)

        assert isinstance(tbl.data_source, XlsxUrlDataSource)


class TestTablesPreviewTableName:
    """The name namespaces the state the frontend persists per table, so it is per sheet."""

    def test_first_sheet_keeps_the_sheetless_name(self):
        assert tables_preview_table_name("res-1", "view-1") == "preview_resource_res-1_view-1"
        assert tables_preview_table_name("res-1", "view-1", 0) == "preview_resource_res-1_view-1"

    def test_other_sheets_get_their_own_name(self):
        assert tables_preview_table_name("res-1", "view-1", 2) == "preview_resource_res-1_view-1_sheet_2"


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("clear_cache", "clean_redis", "with_plugins", "with_request_context")
class TestTablesInitTemporaryPreviewTableSheets:
    """A workbook resource previews one sheet at a time, chosen by index."""

    @pytest.fixture
    def workbook_view(self, tmp_path):
        """A view pointing at a real two-sheet workbook, fetched without the network."""
        path = tmp_path / "workbook.xlsx"

        with pd.ExcelWriter(path) as writer:
            pd.DataFrame([{"name": "Alice"}]).to_excel(writer, sheet_name="People", index=False)
            pd.DataFrame([{"city": "Kyiv"}]).to_excel(writer, sheet_name="Other Places", index=False)

        with mock.patch(
            "ckanext.tables.data_sources.fetch_remote_file",
            return_value=contextlib.nullcontext(str(path)),
        ):
            yield {"id": "view-1", "file_url": "http://example.com/workbook.xlsx"}

    def _resource(self):
        return {"id": "res-1", "format": "XLSX", "url": "http://example.com/workbook.xlsx"}

    def test_sheets_are_offered_to_the_template(self, workbook_view):
        tbl = tables_init_temporary_preview_table(self._resource(), workbook_view)

        assert tbl.sheets == ["People", "Other Places"]
        assert tbl.current_sheet == 0
        assert [col.field for col in tbl.columns] == ["name"]

    def test_a_multi_sheet_workbook_gets_a_sheet_switch_url(self, workbook_view):
        """The client fetches this (appending its own ?sheet=) to switch sheets without a page reload."""
        tbl = tables_init_temporary_preview_table(self._resource(), workbook_view)

        assert tbl.sheet_switch_url is not None
        assert "res-1" in tbl.sheet_switch_url
        assert "view-1" in tbl.sheet_switch_url
        assert "sheet" not in tbl.sheet_switch_url

    def test_the_selected_sheet_drives_name_columns_and_ajax_url(self, workbook_view):
        tbl = tables_init_temporary_preview_table(self._resource(), workbook_view, 1)

        assert tbl.current_sheet == 1
        assert tbl.name.endswith("_sheet_1")
        assert [col.field for col in tbl.columns] == ["city"]
        assert "sheet=1" in tbl.ajax_url

    def test_a_sheet_that_is_no_longer_there_falls_back_to_the_first(self, workbook_view):
        """A bookmarked link to a since-removed sheet shows the workbook, not an error."""
        tbl = tables_init_temporary_preview_table(self._resource(), workbook_view, 9)

        assert tbl.current_sheet == 0
        assert [col.field for col in tbl.columns] == ["name"]

    def test_a_format_without_sheets_offers_none(self):
        resource = {"id": "res-2", "format": "CSV", "url": "http://example.com/data.csv"}

        with (
            mock.patch(
                "ckanext.tables.data_sources.fetch_remote_file",
                return_value=contextlib.nullcontext("/tmp/mocked-source"),
            ),
            mock.patch("ckanext.tables.data_sources.pd.read_csv", return_value=pd.DataFrame({"a": [1]})),
        ):
            tbl = tables_init_temporary_preview_table(resource, {"id": "view-2"})

        assert tbl.sheets == []
        assert tbl.name == "preview_resource_res-2_view-2"
        assert tbl.sheet_switch_url is None
