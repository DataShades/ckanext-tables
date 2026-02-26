import json
import urllib.parse

import pytest

from ckanext.tables.utils import CacheManager, parse_tabulator_filters, tables_build_params


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
