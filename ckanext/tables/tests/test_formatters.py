from unittest import mock

import pytest

import ckan.tests.factories as factories

from ckanext.tables import formatters, table


def _make_col(field="col", **kwargs):
    return table.ColumnDefinition(field=field, **kwargs)


def _make_table(name="test_table"):
    from ckanext.tables.data_sources import ListDataSource

    return table.TableDefinition(
        name=name,
        data_source=ListDataSource([]),
    )


def _fmt(formatter_class, value, options=None, col=None, row=None, tbl=None):
    """Instantiate a formatter and call format()."""
    col = col or _make_col()
    row = row or {}
    tbl = tbl or _make_table()
    return formatter_class(col, row, row, tbl).format(value, options or {})


class TestBooleanFormatter:
    def test_truthy(self):
        assert _fmt(formatters.BooleanFormatter, True) == "Yes"

    def test_falsy(self):
        assert _fmt(formatters.BooleanFormatter, False) == "No"

    def test_none(self):
        assert _fmt(formatters.BooleanFormatter, None) == "No"


class TestListFormatter:
    def test_list(self):
        assert _fmt(formatters.ListFormatter, [1, 2, 3]) == "1, 2, 3"

    def test_empty_list(self):
        assert _fmt(formatters.ListFormatter, []) == ""

    def test_non_list(self):
        assert _fmt(formatters.ListFormatter, "not a list") == ""

    def test_none(self):
        assert _fmt(formatters.ListFormatter, None) == ""


class TestNoneAsEmptyFormatter:
    def test_none_becomes_empty(self):
        assert _fmt(formatters.NoneAsEmptyFormatter, None) == ""

    def test_value_passthrough(self):
        assert _fmt(formatters.NoneAsEmptyFormatter, "hello") == "hello"

    def test_zero_passthrough(self):
        assert _fmt(formatters.NoneAsEmptyFormatter, 0) == 0


class TestTrimStringFormatter:
    def test_short_string_unchanged(self):
        result = _fmt(formatters.TrimStringFormatter, "hello", {"max_length": 10})
        assert result == "hello"

    def test_long_string_trimmed_with_ellipsis(self):
        result = _fmt(formatters.TrimStringFormatter, "a" * 100, {"max_length": 5})
        assert result == "aaaaa..."

    def test_long_string_no_ellipsis(self):
        result = _fmt(
            formatters.TrimStringFormatter,
            "a" * 100,
            {"max_length": 5, "add_ellipsis": False},
        )
        assert result == "aaaaa"

    def test_non_string_returns_empty(self):
        assert _fmt(formatters.TrimStringFormatter, 123) == ""

    def test_none_returns_empty(self):
        assert _fmt(formatters.TrimStringFormatter, None) == ""

    def test_default_max_length(self):
        long_str = "x" * 80
        result = _fmt(formatters.TrimStringFormatter, long_str)
        # Default max_length is 79
        assert result == "x" * 79 + "..."


class TestURLFormatter:
    def test_url_link(self):
        result = _fmt(formatters.URLFormatter, "http://example.com")
        assert "http://example.com" in result
        assert "<a href=" in result

    def test_custom_target(self):
        result = _fmt(
            formatters.URLFormatter,
            "http://example.com",
            {"target": "_self"},
        )
        assert "_self" in result

    def test_empty_value(self):
        assert _fmt(formatters.URLFormatter, "") == ""

    def test_none_value(self):
        assert _fmt(formatters.URLFormatter, None) == ""

    def test_javascript_scheme_not_rendered_as_link(self):
        result = _fmt(formatters.URLFormatter, "javascript:alert(1)")
        assert "<a" not in result

    def test_value_with_no_scheme_not_rendered_as_link(self):
        result = _fmt(formatters.URLFormatter, "example.com")
        assert "<a" not in result

    def test_protocol_relative_value_not_rendered_as_link(self):
        result = _fmt(formatters.URLFormatter, "//evil.com/phish")
        assert "<a" not in result

    def test_html_injection_in_value_is_escaped(self):
        result = _fmt(formatters.URLFormatter, "'><img src=x onerror=alert(1)>")
        assert "<img" not in result
        assert "&lt;img" in result

    def test_quote_breakout_in_url_is_escaped(self):
        result = _fmt(formatters.URLFormatter, 'http://example.com/"><script>alert(1)</script>')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestTextBoldFormatter:
    def test_wraps_in_strong(self):
        result = _fmt(formatters.TextBoldFormatter, "important")
        assert "<strong>important</strong>" in result

    def test_empty_returns_empty(self):
        assert _fmt(formatters.TextBoldFormatter, "") == ""

    def test_none_returns_empty(self):
        assert _fmt(formatters.TextBoldFormatter, None) == ""

    def test_html_injection_is_escaped(self):
        result = _fmt(formatters.TextBoldFormatter, "<img src=x onerror=alert(1)>")
        assert "<img" not in result
        assert "&lt;img" in result


@pytest.mark.usefixtures("with_request_context")
class TestDateFormatter:
    def test_format_datetime(self):
        from datetime import datetime  # noqa: DTZ001

        dt = datetime(2024, 3, 25, 14, 30)
        result = _fmt(formatters.DateFormatter, dt, {"date_format": "%Y-%m-%d"})
        assert "2024-03-25" in result

    def test_format_iso_string(self):
        # The demo (and most real data sources) hand this an ISO string, not a
        # datetime object — CKAN's render_datetime parses it either way.
        result = _fmt(formatters.DateFormatter, "2024-03-25T14:30:00", {"date_format": "%Y-%m-%d"})
        assert "2024-03-25" in result

    def test_malformed_string_returns_empty_rather_than_raising(self):
        assert _fmt(formatters.DateFormatter, "not a date", {"date_format": "%Y-%m-%d"}) == ""


@pytest.mark.usefixtures("with_request_context", "clean_db")
class TestUserLinkFormatter:
    def test_unknown_user_returns_value_as_str(self):
        result = _fmt(formatters.UserLinkFormatter, "nonexistent-id")
        assert result == "nonexistent-id"

    def test_none_value_returns_empty(self):
        assert _fmt(formatters.UserLinkFormatter, None) == ""

    def test_empty_value_returns_empty(self):
        assert _fmt(formatters.UserLinkFormatter, "") == ""

    def test_memoizes_repeated_lookups_of_the_same_user(self):
        """A user id that recurs across rows must only be looked up once per table."""
        user = factories.User()
        tbl = _make_table()

        with mock.patch.object(formatters.model.User, "get", wraps=formatters.model.User.get) as spy:
            first = _fmt(formatters.UserLinkFormatter, user["id"], tbl=tbl)
            second = _fmt(formatters.UserLinkFormatter, user["id"], tbl=tbl)

        assert first == second
        assert spy.call_count == 1

    def test_memoizes_a_none_result_for_an_unknown_user(self):
        tbl = _make_table()

        with mock.patch.object(formatters.model.User, "get", wraps=formatters.model.User.get) as spy:
            _fmt(formatters.UserLinkFormatter, "nonexistent-id", tbl=tbl)
            _fmt(formatters.UserLinkFormatter, "nonexistent-id", tbl=tbl)

        assert spy.call_count == 1

    def test_separate_tables_do_not_share_the_cache(self):
        user = factories.User()

        with mock.patch.object(formatters.model.User, "get", wraps=formatters.model.User.get) as spy:
            _fmt(formatters.UserLinkFormatter, user["id"], tbl=_make_table("t1"))
            _fmt(formatters.UserLinkFormatter, user["id"], tbl=_make_table("t2"))

        assert spy.call_count == 2


@pytest.mark.usefixtures("with_request_context")
class TestActionsFormatter:
    def test_default_template_is_rendered_once_per_table_and_column(self):
        """The bundled default template never varies by row -- cache its output."""
        tbl = _make_table()
        col = _make_col()

        with mock.patch.object(formatters.tk, "render", return_value="<div>actions</div>") as mock_render:
            first = _fmt(formatters.ActionsFormatter, None, col=col, tbl=tbl)
            second = _fmt(formatters.ActionsFormatter, None, col=col, tbl=tbl)

        assert first == second
        assert mock_render.call_count == 1

    def test_custom_template_is_rendered_every_time(self):
        """A custom template might legitimately vary by row, so it's never cached."""
        tbl = _make_table()
        col = _make_col()
        options = {"template": "tables/formatters/custom.html"}

        with mock.patch.object(formatters.tk, "render", return_value="<div>x</div>") as mock_render:
            _fmt(formatters.ActionsFormatter, None, options=options, col=col, tbl=tbl)
            _fmt(formatters.ActionsFormatter, None, options=options, col=col, tbl=tbl)

        assert mock_render.call_count == 2

    def test_different_columns_are_cached_separately(self):
        tbl = _make_table()

        with mock.patch.object(formatters.tk, "render", return_value="<div>x</div>") as mock_render:
            _fmt(formatters.ActionsFormatter, None, col=_make_col("a"), tbl=tbl)
            _fmt(formatters.ActionsFormatter, None, col=_make_col("b"), tbl=tbl)

        assert mock_render.call_count == 2

    def test_separate_tables_do_not_share_the_cache(self):
        col = _make_col()

        with mock.patch.object(formatters.tk, "render", return_value="<div>x</div>") as mock_render:
            _fmt(formatters.ActionsFormatter, None, col=col, tbl=_make_table("t1"))
            _fmt(formatters.ActionsFormatter, None, col=col, tbl=_make_table("t2"))

        assert mock_render.call_count == 2


@pytest.mark.usefixtures("with_request_context")
class TestJsonDisplayFormatter:
    def test_dict_rendered_as_json(self):
        result = _fmt(formatters.JsonDisplayFormatter, {"a": 1, "b": [2, 3]})
        assert '"a": 1' in result
        assert '"b": [' in result

    def test_list_rendered_as_json(self):
        result = _fmt(formatters.JsonDisplayFormatter, [1, "two", None])
        assert "two" in result

    def test_none(self):
        result = _fmt(formatters.JsonDisplayFormatter, None)
        assert "null" in result


@pytest.mark.usefixtures("with_request_context")
class TestDialogModalFormatter:
    def test_none_returns_empty(self):
        assert _fmt(formatters.DialogModalFormatter, None) == ""

    def test_short_string_shown_inline_without_a_modal(self):
        result = _fmt(formatters.DialogModalFormatter, "short", {"max_length": 100})
        assert "dialog" not in result.lower()
        assert "short" in result

    def test_long_string_gets_a_modal(self):
        result = _fmt(formatters.DialogModalFormatter, "a" * 200, {"max_length": 10})
        assert "<dialog" in result

    def test_custom_modal_title(self):
        result = _fmt(
            formatters.DialogModalFormatter,
            "a" * 200,
            {"max_length": 10, "modal_title": "Row Details"},
        )
        assert "Row Details" in result

    # Non-string, non-falsy values (an int/float/bool cell) used to raise
    # TypeError from the template's `value | length` check.
    def test_non_string_int_does_not_raise(self):
        result = _fmt(formatters.DialogModalFormatter, 424242424242, {"max_length": 5})
        assert "<dialog" in result

    def test_non_string_float_does_not_raise(self):
        result = _fmt(formatters.DialogModalFormatter, 3.14159265, {"max_length": 100})
        assert "3.14" in result

    def test_non_string_bool_does_not_raise(self):
        result = _fmt(formatters.DialogModalFormatter, True, {"max_length": 100})
        assert "True" in result
