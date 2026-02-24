import pytest

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


class TestTextBoldFormatter:
    def test_wraps_in_strong(self):
        result = _fmt(formatters.TextBoldFormatter, "important")
        assert "<strong>important</strong>" in result

    def test_empty_returns_empty(self):
        assert _fmt(formatters.TextBoldFormatter, "") == ""

    def test_none_returns_empty(self):
        assert _fmt(formatters.TextBoldFormatter, None) == ""


@pytest.mark.usefixtures("with_request_context")
class TestDateFormatter:
    def test_format_datetime(self):
        from datetime import datetime  # noqa: DTZ001

        dt = datetime(2024, 3, 25, 14, 30)
        result = _fmt(formatters.DateFormatter, dt, {"date_format": "%Y-%m-%d"})
        assert "2024-03-25" in result


@pytest.mark.usefixtures("with_request_context", "clean_db")
class TestUserLinkFormatter:
    def test_unknown_user_returns_value_as_str(self):
        result = _fmt(formatters.UserLinkFormatter, "nonexistent-id")
        assert result == "nonexistent-id"

    def test_none_value_returns_empty(self):
        assert _fmt(formatters.UserLinkFormatter, None) == ""

    def test_empty_value_returns_empty(self):
        assert _fmt(formatters.UserLinkFormatter, "") == ""
