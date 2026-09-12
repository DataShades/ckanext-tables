import pytest

from ckanext.tables.data_sources import (
    CsvUrlDataSource,
    DataStoreDataSource,
    FeatherUrlDataSource,
    OrcUrlDataSource,
    ParquetUrlDataSource,
    XlsxUrlDataSource,
)
from ckanext.tables.helpers import (
    tables_generate_unique_id,
    tables_get_columns_visibility_from_request,
    tables_get_filters_from_request,
    tables_guess_data_source,
    tables_init_temporary_preview_table,
    tables_json_dumps,
)
from ckanext.tables.shared import ALL_EXPORTERS


class TestTablesJsonDumps:
    def test_simple_dict(self):
        result = tables_json_dumps({"a": 1})
        assert result == '{"a": 1}'

    def test_list(self):
        result = tables_json_dumps([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_string(self):
        result = tables_json_dumps("hello")
        assert result == '"hello"'


class TestTablesGenerateUniqueId:
    def test_returns_string(self):
        uid = tables_generate_unique_id()
        assert isinstance(uid, str)

    def test_unique_each_call(self):
        ids = {tables_generate_unique_id() for _ in range(100)}
        assert len(ids) == 100


class TestTablesGetFiltersFromRequest:
    """Uses real Flask request contexts instead of mocking tk.request."""

    def test_no_params_empty_list(self, app):
        with app.flask_app.test_request_context("/"):
            result = tables_get_filters_from_request()
            assert result == []

    def test_with_filter_params(self, app):
        qs = "/?field=name&operator=%3D&value=Alice"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request()
            assert len(result) == 1
            assert result[0].field == "name"
            assert result[0].operator == "="
            assert result[0].value == "Alice"

    def test_multiple_filters(self, app):
        qs = "/?field=name&operator=%3D&value=Alice&field=age&operator=%3E&value=25"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request()
            assert len(result) == 2
            assert result[0].field == "name"
            assert result[1].field == "age"

    def test_incomplete_filter_ignored(self, app):
        qs = "/?field=name&operator=%3D"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request()
            assert result == []

    def test_non_filter_key_ignored(self, app):
        qs = "/?page=1&size=10"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request()
            assert result == []


class TestColumnsVisibility:
    """Uses real Flask request contexts instead of mocking tk.request."""

    def test_no_params_empty_dict(self, app):
        with app.flask_app.test_request_context("/"):
            result = tables_get_columns_visibility_from_request()
            assert result == {}

    def test_hidden_columns(self, app):
        qs = "/?hidden_column=name&hidden_column=age"
        with app.flask_app.test_request_context(qs):
            result = tables_get_columns_visibility_from_request()
            assert result == {"name": False, "age": False}


class TestTablesGuessDataSource:
    def test_csv_format(self):
        resource = {"format": "CSV", "url": "http://example.com/data.csv", "id": "res-1"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, CsvUrlDataSource)

    def test_xlsx_format(self):
        resource = {"format": "XLSX", "url": "http://example.com/data.xlsx", "id": "res-2"}
        ds = tables_guess_data_source(resource)
        assert isinstance(ds, XlsxUrlDataSource)

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

        with pytest.raises(ValueError, match="Unsupported format"):
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
        with pytest.raises(ValueError, match="Unsupported format"):
            tables_guess_data_source(resource, resource_view)


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

        tbl = tables_init_temporary_preview_table(resource, resource_view)

        from ckanext.tables.data_sources import XlsxUrlDataSource

        assert isinstance(tbl.data_source, XlsxUrlDataSource)
