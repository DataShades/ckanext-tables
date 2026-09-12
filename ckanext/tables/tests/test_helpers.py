from ckanext.tables.helpers import (
    tables_generate_unique_id,
    tables_get_columns_visibility_from_request,
    tables_get_filters_from_request,
    tables_json_dumps,
)


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
