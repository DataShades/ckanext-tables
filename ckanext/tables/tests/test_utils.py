import json
import urllib.parse

from ckanext.tables.utils import parse_tabulator_filters, tables_build_params


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
