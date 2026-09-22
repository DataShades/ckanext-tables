import pytest

from ckanext.tables.helpers import (
    tables_column_actions_field,
    tables_deferred_url,
    tables_filter_operators,
    tables_generate_unique_id,
    tables_get_columns_visibility_from_request,
    tables_get_filters_from_request,
    tables_json_dumps,
    tables_requested_sheet,
)
from ckanext.tables.table import COLUMN_ACTIONS_FIELD
from ckanext.tables.types import FILTER_OPERATORS


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
            result = tables_get_filters_from_request("my_table")
            assert result == []

    def test_with_filter_params(self, app):
        qs = "/?field-my_table=name&operator-my_table=%3D&value-my_table=Alice"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request("my_table")
            assert len(result) == 1
            assert result[0].field == "name"
            assert result[0].operator == "="
            assert result[0].value == "Alice"

    def test_multiple_filters(self, app):
        qs = (
            "/?field-my_table=name&operator-my_table=%3D&value-my_table=Alice"
            "&field-my_table=age&operator-my_table=%3E&value-my_table=25"
        )
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request("my_table")
            assert len(result) == 2
            assert result[0].field == "name"
            assert result[1].field == "age"

    def test_incomplete_filter_ignored(self, app):
        qs = "/?field-my_table=name&operator-my_table=%3D"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request("my_table")
            assert result == []

    def test_non_filter_key_ignored(self, app):
        qs = "/?page=1&size=10"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request("my_table")
            assert result == []

    def test_namespaced_by_table_name(self, app):
        """A filter param for a different table must not leak in."""
        qs = "/?field-other_table=name&operator-other_table=%3D&value-other_table=Alice"
        with app.flask_app.test_request_context(qs):
            result = tables_get_filters_from_request("my_table")
            assert result == []


class TestColumnsVisibility:
    """Uses real Flask request contexts instead of mocking tk.request."""

    def test_no_params_empty_dict(self, app):
        with app.flask_app.test_request_context("/"):
            result = tables_get_columns_visibility_from_request("my_table")
            assert result == {}

    def test_hidden_columns(self, app):
        qs = "/?hidden_column-my_table=name&hidden_column-my_table=age"
        with app.flask_app.test_request_context(qs):
            result = tables_get_columns_visibility_from_request("my_table")
            assert result == {"name": False, "age": False}

    def test_namespaced_by_table_name(self, app):
        """A hidden-column param for a different table must not leak in."""
        qs = "/?hidden_column-other_table=name"
        with app.flask_app.test_request_context(qs):
            result = tables_get_columns_visibility_from_request("my_table")
            assert result == {}


class TestTablesColumnActionsField:
    def test_matches_the_table_module_constant(self):
        assert tables_column_actions_field() == COLUMN_ACTIONS_FIELD


@pytest.mark.usefixtures("with_request_context")
class TestTablesFilterOperators:
    def test_values_match_the_canonical_list(self):
        result = tables_filter_operators()
        assert [op["value"] for op in result] == [value for value, _label in FILTER_OPERATORS]

    def test_labels_are_translated_strings(self):
        result = tables_filter_operators()
        assert all(isinstance(op["label"], str) and op["label"] for op in result)


class TestTablesRequestedSheet:
    """Uses real Flask request contexts instead of mocking tk.request."""

    def test_no_param_is_the_first_sheet(self, app):
        with app.flask_app.test_request_context("/"):
            assert tables_requested_sheet() == 0

    def test_reads_the_index(self, app):
        with app.flask_app.test_request_context("/?sheet=2"):
            assert tables_requested_sheet() == 2

    def test_a_non_numeric_index_is_the_first_sheet(self, app):
        with app.flask_app.test_request_context("/?sheet=People"):
            assert tables_requested_sheet() == 0

    def test_a_negative_index_is_the_first_sheet(self, app):
        with app.flask_app.test_request_context("/?sheet=-3"):
            assert tables_requested_sheet() == 0


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins")
class TestTablesDeferredUrl:
    """The initial htmx load (table_preview.html) needs the *current* page's own state.

    Uses real Flask request contexts, and the real blueprint route (hence the tables
    plugin), so this exercises ``tk.url_for``/``tk.request.query_string`` exactly as
    the app does.
    """

    def test_no_query_string_is_just_the_bare_deferred_url(self, app):
        with app.flask_app.test_request_context("/dataset/x/resource/res-1"):
            url = tables_deferred_url("res-1", "view-1")

        assert url == "/resource-table-deferred/res-1/view-1"

    def test_carries_the_full_current_query_string_verbatim(self, app):
        qs = "sheet=2&hidden_column-my_table=age&page-my_table=3"
        with app.flask_app.test_request_context(f"/dataset/x/resource/res-1?{qs}"):
            url = tables_deferred_url("res-1", "view-1")

        assert url == f"/resource-table-deferred/res-1/view-1?{qs}"

    def test_uses_the_given_resource_and_view_ids(self, app):
        with app.flask_app.test_request_context("/dataset/x/resource/res-2"):
            url = tables_deferred_url("res-2", "view-2")

        assert "res-2" in url
        assert "view-2" in url
