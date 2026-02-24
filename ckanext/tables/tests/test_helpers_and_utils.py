import json
import urllib.parse

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
    tables_json_dumps,
)
from ckanext.tables.utils import CacheManager, parse_tabulator_filters, tables_build_params


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


@pytest.mark.usefixtures("clean_redis")
class TestCacheManager:
    def test_save_and_get(self):
        manager = CacheManager(cache_ttl=60)
        manager.save("my_table", {"col": "val", "page": 1})
        result = manager.get("my_table")
        assert result == {"col": "val", "page": 1}

    def test_get_missing_returns_empty_dict(self):
        manager = CacheManager()
        result = manager.get("nonexistent_table")
        assert result == {}

    def test_delete(self):
        manager = CacheManager(cache_ttl=60)
        manager.save("del_table", {"x": "y"})
        manager.delete("del_table")
        result = manager.get("del_table")
        assert result == {}

    def test_key_prefix(self):
        manager = CacheManager()
        assert manager._key("foo") == "ckanext:tables:table:foo"
